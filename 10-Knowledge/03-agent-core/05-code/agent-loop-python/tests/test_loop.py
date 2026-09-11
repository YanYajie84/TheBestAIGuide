import json
from pathlib import Path
import tempfile
import time
import unittest
from agent_loop import (
    Action,
    ApprovalDecision,
    EvidenceModel,
    ModelDecision,
    OpenAICompatibleAdapter,
    Plan,
    PlanStep,
    ScriptedModel,
    Tool,
    Usage,
    default_tools,
    execute_plan,
    load_checkpoint,
    replan,
    resume_agent,
    run_agent,
    run_revision_loop,
    save_checkpoint,
)
from agent_loop.eval import evaluate


class LoopTests(unittest.TestCase):
    def test_evidence_and_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "trace.jsonl")
            state = run_agent(
                EvidenceModel(), default_tools(), "上下文", trace_path=path
            )
            self.assertEqual(state.status, "completed")
            self.assertIn("[doc-1]", state.answer)
            events = [
                json.loads(line)
                for line in Path(path).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([e["seq"] for e in events], list(range(len(events))))
            self.assertEqual(events[-1]["kind"], "run_finished")

    def test_invalid_model(self):
        state = run_agent(ScriptedModel([Action("invented")]), {}, "test")
        self.assertEqual(state.stop_reason, "invalid_model_output")

    def test_tool_error_is_observation(self):
        state = run_agent(
            ScriptedModel(
                [
                    Action("tool", "search", {"query": 2}),
                    Action("finish", answer="invalid"),
                ]
            ),
            default_tools(),
            "x",
        )
        self.assertEqual(state.observations[0]["error"]["code"], "invalid_arguments")

    def test_no_progress(self):
        actions = [Action("tool", "search", {"query": "上下文"})] * 5
        state = run_agent(ScriptedModel(actions), default_tools(), "x")
        self.assertEqual(state.stop_reason, "no_progress")
        self.assertEqual(state.steps, 2)

    def test_budget(self):
        state = run_agent(
            ScriptedModel([Action("tool", "search", {"query": "上下文"})]),
            default_tools(),
            "x",
            max_steps=1,
        )
        self.assertEqual(state.stop_reason, "max_steps")

    def test_permission_and_unknown(self):
        for tools, code in [
            ({}, "unknown_tool"),
            ({"x": Tool(lambda a: 1, allowed=False)}, "permission_denied"),
        ]:
            state = run_agent(
                ScriptedModel([Action("tool", "x"), Action("finish", answer="stop")]),
                tools,
                "x",
            )
            self.assertEqual(state.observations[0]["error"]["code"], code)

    def test_model_cannot_mutate_state(self):
        class BadModel:
            def decide(self, state):
                state.observations.append({"fake": True})
                return Action("finish", answer="done")

        self.assertEqual(run_agent(BadModel(), {}, "x").observations, [])

    def test_non_json_arguments_and_output_stay_in_error_boundary(self):
        invalid = Action("tool", "x", {"query": "test", 2: 3})
        state = run_agent(ScriptedModel([invalid]), {}, "x")
        self.assertEqual(state.stop_reason, "invalid_model_output")
        with tempfile.TemporaryDirectory() as folder:
            trace = str(Path(folder) / "trace.jsonl")
            state = run_agent(
                ScriptedModel(
                    [Action("tool", "x"), Action("finish", answer="bad output")]
                ),
                {"x": Tool(lambda _: {"normal": 1, 2: 3})},
                "x",
                trace_path=trace,
            )
            self.assertEqual(state.observations[0]["error"]["code"], "invalid_output")
            self.assertEqual(
                json.loads(Path(trace).read_text(encoding="utf-8").splitlines()[-1])[
                    "kind"
                ],
                "run_finished",
            )

    def test_tool_mutation_cannot_rewrite_previous_observations_or_events(self):
        shared = {"value": 1}

        def mutate(_):
            shared["value"] = 9
            return shared

        actions = [
            Action("tool", "read"),
            Action("tool", "mutate"),
            Action("finish", answer="done"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            trace = str(Path(folder) / "trace.jsonl")
            state = run_agent(
                ScriptedModel(actions),
                {"read": Tool(lambda _: shared), "mutate": Tool(mutate)},
                "x",
                trace_path=trace,
            )
            self.assertEqual([o["data"]["value"] for o in state.observations], [1, 9])
            events = [
                json.loads(line)
                for line in Path(trace).read_text(encoding="utf-8").splitlines()
            ]
            results = [
                e["data"]["data"]["value"] for e in events if e["kind"] == "tool_result"
            ]
            self.assertEqual(results, [1, 9])

    def test_history_keeps_action_and_observation_together(self):
        state = run_agent(EvidenceModel(), default_tools(), "上下文")
        self.assertEqual(state.history[0].action.name, "search")
        self.assertEqual(state.history[0].action.arguments, {"query": "上下文"})
        self.assertEqual(state.history[0].observation, state.observations[0])
        self.assertGreaterEqual(state.history[0].duration_ms, 0)

    def test_usage_budget(self):
        class MeteredModel:
            def decide(self, state):
                return ModelDecision(
                    Action("tool", "search", {"query": "上下文"}), Usage(8, 4)
                )

        state = run_agent(MeteredModel(), default_tools(), "x", max_total_tokens=10)
        self.assertEqual(state.stop_reason, "token_budget")
        self.assertEqual(state.usage.total_tokens, 12)
        self.assertEqual(state.observations, [])

    def test_approval_binds_and_resumes_exact_action(self):
        calls = []
        tools = {
            "publish": Tool(
                lambda args: calls.append(args) or {"published": True},
                requires_approval=True,
                side_effecting=True,
                require_idempotency_key=True,
            )
        }
        model = ScriptedModel(
            [
                Action(
                    "tool", "publish", {"idempotency_key": "task-1", "text": "draft"}
                ),
                Action("finish", answer="published"),
            ]
        )
        waiting = run_agent(model, tools, "publish")
        self.assertEqual(waiting.status, "waiting_for_input")
        self.assertEqual(calls, [])
        decision_id = waiting.pending_approval["decision_id"]
        completed = resume_agent(
            model, tools, waiting, ApprovalDecision(decision_id, True)
        )
        self.assertEqual(completed.status, "completed")
        self.assertEqual(calls[0]["text"], "draft")
        with self.assertRaises(ValueError):
            resume_agent(model, tools, waiting, ApprovalDecision("wrong", True))

    def test_side_effect_requires_idempotency_key(self):
        tool = Tool(
            lambda _: {"ok": True}, side_effecting=True, require_idempotency_key=True
        )
        state = run_agent(
            ScriptedModel([Action("tool", "write"), Action("finish", answer="stop")]),
            {"write": tool},
            "x",
        )
        self.assertEqual(
            state.observations[0]["error"]["code"], "idempotency_key_required"
        )

    def test_timeout_marks_side_effect_uncertain(self):
        tool = Tool(
            lambda _: time.sleep(0.05), timeout_seconds=0.001, side_effecting=True
        )
        state = run_agent(
            ScriptedModel([Action("tool", "slow"), Action("finish", answer="stop")]),
            {"slow": tool},
            "x",
        )
        self.assertEqual(
            state.observations[0]["error"]["code"], "timeout_side_effect_unknown"
        )
        self.assertTrue(state.observations[0]["error"]["side_effect_unknown"])

    def test_openai_compatible_adapter_parses_tool_then_finish(self):
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"query":"上下文"}',
                                    },
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
            {
                "choices": [{"message": {"content": "done"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 1},
            },
        ]
        seen_payloads = []

        def transport(url, headers, payload, timeout):
            seen_payloads.append(payload)
            return responses.pop(0)

        tools = default_tools()
        model = OpenAICompatibleAdapter(
            base_url="https://example.invalid/v1",
            api_key="secret",
            model="test",
            tools=tools,
            transport=transport,
        )
        state = run_agent(model, tools, "上下文")
        self.assertEqual(state.answer, "done")
        self.assertEqual(state.usage.total_tokens, 16)
        self.assertEqual(seen_payloads[1]["messages"][-1]["role"], "tool")

    def test_adapter_rejects_truncated_response(self):
        model = OpenAICompatibleAdapter(
            base_url="https://example.invalid/v1",
            api_key="secret",
            model="test",
            tools=default_tools(),
            transport=lambda *_: {
                "choices": [
                    {"finish_reason": "length", "message": {"content": "partial"}}
                ]
            },
        )
        state = run_agent(model, default_tools(), "x")
        self.assertEqual(state.stop_reason, "invalid_model_output")

    def test_revision_loop_is_bounded(self):
        candidates = iter(["missing", "has citation [doc-1]"])
        result = run_revision_loop(
            lambda feedback: next(candidates),
            lambda text: {"passed": "[doc-1]" in text},
            max_revisions=1,
        )
        self.assertEqual(result.attempts, 2)
        self.assertTrue(result.verdict["passed"])

    def test_synthetic_fixture_eval(self):
        fixture = Path(__file__).parents[1] / "fixtures" / "teaching-tasks.json"
        result = evaluate(fixture)
        self.assertEqual(result["passed"], result["total"])

    def test_checkpoint_round_trip_preserves_history_and_approval(self):
        tools = {"publish": Tool(lambda _: {"ok": True}, requires_approval=True)}
        waiting = run_agent(
            ScriptedModel([Action("tool", "publish", {"text": "草稿"})]), tools, "发布"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            save_checkpoint(waiting, path)
            loaded = load_checkpoint(path)
        self.assertEqual(loaded.pending_approval, waiting.pending_approval)
        self.assertEqual(loaded.status, "waiting_for_input")

    def test_plan_dependencies_and_replan_preserve_accepted_artifacts(self):
        plan = Plan(
            [
                PlanStep("evidence", "预算", acceptance="at least one document"),
                PlanStep("summary", "总结", depends_on=("evidence",)),
            ]
        )
        executed = execute_plan(
            plan,
            lambda step: {"query": step.query},
            lambda step, artifact: step.id == "evidence",
        )
        self.assertEqual(
            [step.status for step in executed.steps], ["accepted", "missing_evidence"]
        )
        updated = replan(
            executed, [PlanStep("evidence", "不应覆盖"), PlanStep("rewrite", "重写")]
        )
        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.steps[0].artifact, {"query": "预算"})

    def test_cancellation_stops_before_model_call(self):
        state = run_agent(
            ScriptedModel([Action("finish", answer="unexpected")]),
            {},
            "x",
            should_cancel=lambda: True,
        )
        self.assertEqual(state.stop_reason, "cancelled")
        self.assertEqual(state.steps, 0)


if __name__ == "__main__":
    unittest.main()

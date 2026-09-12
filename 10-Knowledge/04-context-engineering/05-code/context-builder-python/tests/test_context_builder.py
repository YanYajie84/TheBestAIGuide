import unittest

from context_builder import (
    CandidateRef,
    ChatTemplateCounter,
    ContextBudget,
    ContextConflictError,
    ContextPolicy,
    ContextRequest,
    StructuredEvent,
    TokenizerCounter,
    build_context,
    byte_tokens,
    compact_events,
    evidence_metrics,
)


def candidate(item_id: str, **changes) -> CandidateRef:
    values = {
        "id": item_id,
        "tenant": "alpha",
        "kind": "evidence",
        "trust": "workspace",
        "utility": 1.0,
    }
    values.update(changes)
    return CandidateRef(**values)


class ContextBuilderTests(unittest.TestCase):
    def setUp(self):
        self.request = ContextRequest(
            goal="修复重复入账",
            tenant="alpha",
            constraints=("不得修改生产数据",),
            acceptance=("测试通过",),
        )
        self.budget = ContextBudget(800, 100, 20, 30)

    def test_builds_mandatory_envelope_and_reserves_all_budget_classes(self):
        contents = {"must": "幂等键是硬要求", "nice": "相关运行日志"}
        result = build_context(
            self.request,
            [candidate("nice"), candidate("must", mandatory=True)],
            lambda ref: contents[ref.id],
            self.budget,
        )
        self.assertIn("[goal] 修复重复入账", result.text)
        self.assertIn("[constraint:1] 不得修改生产数据", result.text)
        self.assertEqual(result.selected_ids[0], "must")
        self.assertEqual(result.content_limit, 650)
        self.assertLessEqual(result.input_tokens, result.content_limit)

    def test_policy_rejects_before_content_read(self):
        refs = [
            candidate("ok"),
            candidate("other", tenant="beta"),
            candidate("secret", sensitive=True),
            candidate("untrusted", trust="web"),
            candidate("expired", expires_at="2026-01-01T00:00:00+00:00"),
            candidate("wrong-version", kind="manual", version="v1"),
        ]
        loaded = []

        def loader(ref):
            loaded.append(ref.id)
            return ref.id

        policy = ContextPolicy(
            "alpha",
            as_of="2026-09-11T00:00:00+00:00",
            required_versions=(("manual", "v2"),),
        )
        result = build_context(self.request, refs, loader, self.budget, policy=policy)
        self.assertEqual(loaded, ["ok"])
        self.assertEqual(result.loaded_ids, ["ok"])
        self.assertEqual(
            {row["id"]: row["reason"] for row in result.dropped},
            {
                "other": "permission",
                "secret": "sensitive",
                "untrusted": "trust",
                "expired": "expired",
                "wrong-version": "version",
            },
        )

    def test_duplicate_ids_fail_before_loading(self):
        loaded = []
        with self.assertRaisesRegex(ValueError, "unique"):
            build_context(
                self.request,
                [candidate("same"), candidate("same")],
                lambda ref: loaded.append(ref.id) or "text",
                self.budget,
            )
        self.assertEqual(loaded, [])

    def test_non_finite_utility_fails_before_loading(self):
        loaded = []
        with self.assertRaisesRegex(ValueError, "finite"):
            build_context(
                self.request,
                [candidate("bad", utility=float("nan"))],
                lambda ref: loaded.append(ref.id) or "text",
                self.budget,
            )
        self.assertEqual(loaded, [])

    def test_mandatory_overflow_fails_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError, "mandatory"):
            build_context(
                self.request,
                [candidate("must", mandatory=True)],
                lambda _ref: "x" * 500,
                ContextBudget(100, 10),
            )

    def test_invalid_counter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            build_context(
                self.request,
                [candidate("one")],
                lambda _ref: "text",
                self.budget,
                count=lambda _text: -1,
            )

    def test_exact_duplicate_keeps_mandatory_owner_and_provenance(self):
        result = build_context(
            self.request,
            [candidate("optional"), candidate("must", mandatory=True)],
            lambda _ref: "same text",
            self.budget,
        )
        self.assertEqual(result.selected_ids, ["must"])
        self.assertIn({"id": "optional", "reason": "exact_duplicate"}, result.dropped)
        self.assertEqual(result.transformations[0]["method"], "exact_dedup")
        self.assertEqual(
            set(result.transformations[0]["source_ids"]), {"optional", "must"}
        )

    def test_conflicting_fact_keys_fail_by_default(self):
        refs = [
            candidate("old", fact_key="status"),
            candidate("new", fact_key="status"),
        ]
        with self.assertRaises(ContextConflictError):
            build_context(
                self.request,
                refs,
                lambda ref: {"old": "失败", "new": "成功"}[ref.id],
                self.budget,
            )

    def test_conflicting_fact_keys_can_be_kept_with_warning(self):
        refs = [
            candidate("old", fact_key="status"),
            candidate("new", fact_key="status"),
        ]
        result = build_context(
            self.request,
            refs,
            lambda ref: {"old": "失败", "new": "成功"}[ref.id],
            self.budget,
            policy=ContextPolicy("alpha", conflict_mode="warn_keep_both"),
        )
        self.assertEqual(set(result.selected_ids), {"old", "new"})
        self.assertEqual(len(result.warnings), 1)

    def test_timezone_is_required_for_expiration_checks(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            build_context(
                self.request,
                [candidate("dated", expires_at="2026-01-01T00:00:00")],
                lambda _ref: "text",
                self.budget,
                policy=ContextPolicy("alpha", as_of="2026-09-11T00:00:00+00:00"),
            )


class AdapterTests(unittest.TestCase):
    def test_tokenizer_adapter_uses_provider_encode(self):
        class Provider:
            def encode(self, text):
                return text.split()

        self.assertEqual(TokenizerCounter(Provider().encode)("one two three"), 3)

    def test_chat_template_counter_counts_rendered_messages(self):
        counter = ChatTemplateCounter(
            render=lambda messages, tools: "|".join(
                [
                    *(item["content"] for item in messages),
                    *(tool["name"] for tool in tools),
                ]
            ),
            counter=len,
        )
        self.assertEqual(
            counter.count_request(
                [{"role": "user", "content": "你好"}], [{"name": "search"}]
            ),
            9,
        )

    def test_byte_counter_is_explicit_utf8_teaching_counter(self):
        self.assertEqual(byte_tokens("中"), 3)


class CompactionAndEvaluationTests(unittest.TestCase):
    def test_compaction_is_tenant_scoped_and_constraint_wins(self):
        events = [
            StructuredEvent("c1", "alpha", "constraint", "deploy", "禁止", 1),
            StructuredEvent("o1", "alpha", "observation", "deploy", "允许", 99),
            StructuredEvent("b1", "beta", "constraint", "secret", "泄露", 100),
        ]
        result = compact_events(events, "alpha")
        self.assertEqual(result["facts"], {"deploy": "禁止"})
        self.assertEqual(result["sources"], {"deploy": "c1"})

    def test_newer_event_wins_within_same_kind_and_authority(self):
        events = [
            StructuredEvent("one", "alpha", "observation", "tests", "失败", 1),
            StructuredEvent("two", "alpha", "observation", "tests", "通过", 2),
        ]
        self.assertEqual(compact_events(events, "alpha")["facts"]["tests"], "通过")

    def test_empty_metric_denominators_are_not_applicable(self):
        metrics = evidence_metrics(set(), set())
        self.assertIsNone(metrics.recall)
        self.assertIsNone(metrics.precision)

    def test_evidence_metrics_use_stable_ids(self):
        metrics = evidence_metrics({"e1", "e2"}, {"e2", "noise"})
        self.assertEqual(metrics.recall, 0.5)
        self.assertEqual(metrics.precision, 0.5)


if __name__ == "__main__":
    unittest.main()

"""The model and the manifest, as a pair. C2."""
from __future__ import annotations

import os

import pytest

from conftest import FIXTURE
from factory_line_audit.generator import build, entity_type_for, sanitise

yaml = pytest.importorskip("yaml", reason="a real parser is needed to check "
                                          "what this package's writer emits")


@pytest.fixture
def pair(register, gated):
    text, manifest = build(register, gated)
    return text, manifest, yaml.safe_load(text)


class TestTheWriterEmitsWhatItMeant:
    def test_it_parses_with_a_real_parser(self, pair):
        """The writer is hand-rolled so Stage 1 stays dependency-free. That
        buys a new way to be wrong -- it emitted list items whose continuation
        lines were indented one level short, and the result still parsed, into
        something else."""
        _, _, model = pair
        assert "domain" in model

    def test_every_indicator_survived_as_a_mapping(self, pair):
        _, _, model = pair
        for etype, rows in model["domain"]["indicators"].items():
            assert isinstance(rows, list), etype
            for row in rows:
                assert isinstance(row, dict), (etype, row)
                assert "name" in row and "type" in row
                # `axioms` is absent, not empty, on the output half of a
                # derived balance: an indicator that answers nothing must not
                # be declared as though it answers an empty list.
                if not row["name"].endswith("_per_interval"):
                    assert "axioms" in row, row

    def test_nested_blocks_survived(self, pair):
        _, _, model = pair
        station = model["domain"]["indicators"]["Station__ST_02"]
        cycle = next(r for r in station if r["name"] == "cycle_time_s")
        assert cycle["homeostasis"] == {"setpoint": 60, "tolerance": 4}

    def test_a_shape_the_writer_cannot_represent_is_refused(self):
        from factory_line_audit.generator import _yaml
        with pytest.raises(TypeError):
            _yaml(object())


class TestOneEntityTypePerRealWorldUnit:
    def test_each_asset_gets_its_own_type(self, pair):
        _, manifest, model = pair
        assert len(set(model["domain"]["entity_types"])) == \
            len(model["domain"]["entity_types"])
        assert manifest["entity_type_map"]["Station__ST_01"] == "ST-01"

    def test_the_map_goes_back_to_something_an_operator_says_out_loud(self, pair):
        _, manifest, _ = pair
        assert set(manifest["entity_type_map"].values()) >= {"ST-01", "PR-01"}

    def test_sanitise_is_reversible_through_the_map_not_the_string(self):
        assert sanitise("ST-01") == "ST_01"
        assert entity_type_for({"id": "ST-01", "type": "Station"}) == "Station__ST_01"


class TestExclusionsAreNamedNotSilent:
    def test_an_axiom_with_no_declared_number_is_excluded_with_a_reason(self, pair):
        """Not declared-and-declined. Emitting it would inflate the denominator
        with `no_threshold` declines for a question nobody asked."""
        _, manifest, _ = pair
        rows = [e for e in manifest["exclusions"]
                if e.get("reason") == "no_declared_bound"]
        assert rows
        assert all(e["detail"] for e in rows)

    def test_a_declared_exclusion_carries_its_basis(self, pair):
        _, manifest, _ = pair
        rows = [e for e in manifest["exclusions"]
                if e.get("reason") == "declared_exclusion"]
        assert rows and all(e.get("basis") for e in rows)

    def test_the_excluded_asset_is_not_in_the_model(self, pair):
        _, _, model = pair
        assert not any("MES" in t for t in model["domain"]["entity_types"])

    def test_a_relation_pointing_out_of_the_model_is_excluded_not_declared(
            self, register, gated):
        """Declaring CONNECTIVITY at a type the walk will never produce buys a
        `missing_entity_type` decline instead of a check."""
        _, manifest = build(register, gated)
        assert not any(e["reason"] == "relation_target_excluded"
                       and e["asset"] == "MES-GW" for e in manifest["exclusions"])

    def test_every_exclusion_says_which_scope_it_is(self, pair):
        """Held against the emitting module, not a copy of its list.

        This assertion used to carry the vocabulary inline. A transcribed list
        goes stale on the day a member lands and nothing goes red -- the
        README's list of declaration kinds did exactly that, and sat a member
        short of `KINDS` until a guard was written for it.
        """
        from factory_line_audit.generator import SCOPES
        _, manifest, _ = pair
        for row in manifest["exclusions"]:
            assert row["scope"] in SCOPES

    def test_the_counts_add_up(self, pair):
        _, manifest, model = pair
        counts = manifest["counts"]
        assert counts["assets_modelled"] == len(model["domain"]["entity_types"])
        assert counts["exclusions"] == len(manifest["exclusions"])


class TestWhatTheModelDeclares:
    def test_a_learned_baseline_is_recorded_so_the_exit_can_use_it(self, pair):
        """The finding class needs to know which HOMEOSTASIS cells had no
        setpoint. The engine's finding does not carry that."""
        _, manifest, _ = pair
        assert "ROB-01.joint_torque_nm" in manifest["learned_baselines"]
        assert "ST-01.cycle_time_s" not in manifest["learned_baselines"]

    def test_a_percentage_declares_the_role_rather_than_being_guessed(self, pair):
        _, _, model = pair
        rows = model["domain"]["indicators"]["Station__ST_03"]
        reject = next(r for r in rows if r["name"] == "reject_pct")
        assert reject["role"] == "percentage"
        assert "CONSISTENCY" in reject["axioms"]

    def test_a_state_tag_becomes_no_indicator_at_all(self, pair):
        _, manifest, model = pair
        rows = model["domain"]["indicators"]["Station__ST_01"]
        assert not any(r["name"] == "state_running" for r in rows)
        assert any(e["reason"] == "state_tag_is_not_an_indicator"
                   for e in manifest["exclusions"])

    def test_conservation_balances_the_derived_rate_not_the_counter(self, pair):
        """The engine compares levels at a relative threshold measured
        between 5 % and 8 % (probe K7). Against a lifetime counter that is a loss of hundreds of
        parts, and it gets quieter the longer the line runs. So the balance is
        declared on the first difference, under a derived name."""
        _, manifest, model = pair
        rows = model["domain"]["indicators"]["Station__ST_02"]
        rate = next(r for r in rows if r["name"] == "parts_in_per_interval")
        assert rate["conservation"]["input_property"] == "parts_in_per_interval"
        assert rate["conservation"]["output_properties"] == [
            "parts_out_per_interval", "scrap_count_per_interval"]
        assert rate["flow"] == "in"
        assert next(r for r in rows
                    if r["name"] == "scrap_count_per_interval")["flow"] == "out"
        counter = next(r for r in rows if r["name"] == "parts_in")
        assert "conservation" not in counter

    def test_every_derived_indicator_is_named_in_the_manifest(self, pair):
        """An indicator no operator declared, appearing in a finding, has to be
        traceable to whoever invented it."""
        _, manifest, model = pair
        derived_in_model = {r["name"] for rows in model["domain"]["indicators"].values()
                            for r in rows if r["name"].endswith("_per_interval")}
        declared = " ".join(e["detail"] for e in manifest["exclusions"]
                            if e["reason"] == "derived_per_interval_indicator")
        assert derived_in_model
        for name in derived_in_model:
            assert name in declared, name

    def test_the_counter_it_was_derived_from_says_so(self, pair):
        _, manifest, _ = pair
        rows = [e for e in manifest["exclusions"]
                if e.get("reason") == "balanced_on_the_derived_rate"]
        assert rows and all("K7" in e["detail"] for e in rows)

    def test_an_undeclared_rate_arm_is_recorded_as_running_on_a_default(self, pair):
        """The engine answers this arm from a default rather than declining, so
        nothing else would ever say it happened."""
        _, manifest, _ = pair
        rows = [e for e in manifest["exclusions"]
                if e.get("reason") == "no_declared_rate"]
        assert rows, "no counter is running on the engine's default rate"
        assert all("default" in e["detail"] for e in rows)


class TestTheWriterSurvivesYamlOneOne:
    """The engine loads the model with `yaml.safe_load`, which resolves YAML 1.1.

    A `bad_state` declaring the PLC state word `Off` emitted `bad: [Off, Fault]`
    and the engine read `[False, "Fault"]`. The fed property is the string
    `"Off"`: it never equals `False`, the declared bad state could not fire,
    nothing declined, and probe D1 had already measured that `unread_fields`
    says nothing about `bad:`. Silence that looks like health, arriving through
    the model writer.

    `On` and `Yes` fail the other way round -- they become `True`, which a state
    tag fed a real boolean WOULD match. Both directions are held below.
    """

    #: Derived from the parser, not transcribed. The reserved list in the writer
    #: was lowercase-only for exactly as long as nobody asked PyYAML.
    CANDIDATES = ("y", "Y", "n", "N", "yes", "Yes", "YES", "no", "No", "NO",
                  "true", "True", "TRUE", "false", "False", "FALSE",
                  "on", "On", "ON", "off", "Off", "OFF",
                  "null", "Null", "NULL", "~", ".nan", ".inf", "-.inf",
                  "Fault", "Running", "Stopped", "NUMERIC")

    def _bare(self, word):
        """What the parser makes of the word with no quoting at all."""
        return yaml.safe_load(f"a: {word}\n")["a"]

    def _written(self, word):
        from factory_line_audit.generator import _yaml
        return yaml.safe_load("\n".join(_yaml({"a": word})))["a"]

    def test_the_probe_can_produce_a_positive(self):
        """Before believing the rule below, prove this parser really does read
        some of these as non-strings. On a parser that did not, every assertion
        underneath would pass having measured nothing."""
        coerced = [w for w in self.CANDIDATES
                   if not isinstance(self._bare(w), str)]
        assert len(coerced) >= 20, (
            f"only {coerced} are coerced when written bare; this parser does "
            f"not resolve YAML 1.1 and the rule below is vacuous")

    def test_every_candidate_survives_the_writer_as_the_string_it_was(self):
        for word in self.CANDIDATES:
            assert self._written(word) == word, (
                f"{word!r} was written in a way that parses back as "
                f"{self._written(word)!r}")

    def test_a_declared_bad_state_reaches_the_engine_as_words(self, register,
                                                              tmp_path):
        """End to end through the real gate and the real writer, because the
        rule above is about `_yaml` and the defect was about `bad:`."""
        import json

        from factory_line_audit.declarations import gate
        from factory_line_audit.generator import build
        with open(FIXTURE, encoding="utf-8") as handle:
            body = json.load(handle)
        body["statements"].append(
            {"kind": "bad_state", "asset": "ST-01", "tag": "state_running",
             "states": ["Off", "Fault", "On"],
             "basis": "FIXTURE -- three words a PLC really produces"})
        path = os.path.join(str(tmp_path), "d.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)
        text, _ = build(register, gate([path], register))
        row = next(r for r in yaml.safe_load(text)["domain"]
                   ["indicators"]["Station__ST_01"] if r["name"] == "state_running")
        assert row["bad"] == ["Off", "Fault", "On"], row["bad"]
        assert all(isinstance(word, str) for word in row["bad"])

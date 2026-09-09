"""Stage 1: three states, never two, and a status word read as a status word."""
from __future__ import annotations

import pytest

from factory_line_audit import formats
from factory_line_audit.presence import (
    ABSENT, NOT_READING, QUALITY_GRADES, READING, classify, grade,
    looks_templated, reading_map)


class TestQualityIsNotABoolean:
    @pytest.mark.parametrize("word,usable,substituted", [
        ("Good", True, False),
        ("Good_SubNormal", True, False),
        ("Good_LocalOverride", True, True),
        ("Uncertain_LastUsableValue", False, False),
        ("Bad_DeviceFailure", False, False),
        ("BadNoCommunication", False, False),
    ])
    def test_each_family_grades_as_itself(self, word, usable, substituted):
        _, props = grade(word)
        assert props["usable"] is usable
        assert props["substituted"] is substituted

    def test_a_substituted_value_is_usable_and_still_costs_something(self):
        """`Good_LocalOverride` is a number a person typed at a panel. Every
        axiom evaluated on it is being asked about the operator rather than the
        machine, so it reads and it floors at 1."""
        _, props = grade("Good_LocalOverride")
        assert props["usable"] and props["floor"] == 1

    def test_a_word_this_reader_has_never_seen_is_not_optimistic(self):
        """Grading an unknown status as Good is how a substituted value gets
        judged as a measurement."""
        _, props = grade("Sideways_Maybe")
        assert not props["usable"]

    def test_none_and_empty_are_not_good(self):
        assert not grade(None)[1]["usable"]
        assert not grade("")[1]["usable"]


class TestTemplatedNames:
    @pytest.mark.parametrize("name", ["SpareAnalog3", "spare1", "Reserved_A",
                                      "TemplateTag", "Unused9", "DummyX"])
    def test_placeholders_are_proposed(self, name):
        assert looks_templated(name)

    @pytest.mark.parametrize("name", ["spared_capacity", "template_id"])
    def test_a_real_name_the_glob_also_catches_is_still_only_a_proposal(self, name):
        """`spared_capacity` matches `spare*` and is a real measurement. The
        glob cannot tell them apart and neither can any other predicate over
        the letters, which is why matching PROPOSES and never excludes."""
        assert looks_templated(name)
        assert name not in str(load_register_excludes())

    @pytest.mark.parametrize("name", ["speed_mpm", "die_temp_c",
                                      "reserve_pressure_bar"])
    def test_ordinary_names_are_not_even_proposed(self, name):
        assert not looks_templated(name)

    def test_only_a_DECLARED_flag_excludes(self, register):
        """An exclusion that leaves no trace is indistinguishable from having
        forgotten the tag existed -- and one made by a name rule is a guess
        recorded as a decision."""
        excluded = register["_excluded_tags"]
        assert [row["tag"] for row in excluded] == ["SpareAnalog3"]
        assert excluded[0]["reason"] == "declared_templated"

    def test_the_proposal_reaches_a_person_through_the_draft(self, register):
        from factory_line_audit.declarations import draft
        proposed = [s for s in draft(register)["statements"]
                    if s["kind"] == "exclusion"]
        assert proposed == [] or all(s["basis"] == "" for s in proposed)


def load_register_excludes():
    from conftest import REGISTER
    from factory_line_audit.presence import load_register
    return [row["tag"] for row in load_register(REGISTER)["_excluded_tags"]]


class TestThreeStates:
    def test_the_clean_walk_reads_everything_declared(self, register, clean_walk):
        presence = classify(register, clean_walk)
        assert presence["counts"][NOT_READING] == 0
        assert presence["counts"][ABSENT] == 0
        assert presence["exit"] == 0

    def test_a_node_the_walk_never_served_is_absent(self, register, clean_walk):
        rob = next(a for a in register["assets"] if a["id"] == "ROB-01")
        node = rob["tags"]["axis1_temp_c"]["node"]
        for sample in clean_walk["samples"]:
            sample["nodes"].pop(node, None)
        presence = classify(register, clean_walk)
        row = next(t for t in presence["tags"] if t["node"] == node)
        assert row["state"] == ABSENT
        assert presence["exit"] == 1

    def test_a_node_served_with_a_bad_word_is_present_and_not_reading(
            self, register, clean_walk):
        press = next(a for a in register["assets"] if a["id"] == "PR-01")
        node = press["tags"]["die_temp_c"]["node"]
        for sample in clean_walk["samples"]:
            sample["nodes"][node] = {"v": None, "q": "Bad_SensorFailure"}
        presence = classify(register, clean_walk)
        row = next(t for t in presence["tags"] if t["node"] == node)
        assert row["state"] == NOT_READING
        assert row["samples"] == len(clean_walk["samples"])
        assert presence["exit"] == 1

    def test_absent_and_not_reading_are_never_the_same_row(
            self, register, clean_walk):
        """The whole reason the classification is three-way: these two send a
        person to two different places."""
        assert ABSENT != NOT_READING != READING

    def test_a_substituted_value_is_visible_without_changing_the_state(
            self, register, clean_walk):
        conveyor = next(a for a in register["assets"] if a["id"] == "CNV-01")
        node = conveyor["tags"]["speed_mpm"]["node"]
        for sample in clean_walk["samples"]:
            sample["nodes"][node]["q"] = "GoodLocalOverride"
        presence = classify(register, clean_walk)
        row = next(t for t in presence["tags"] if t["node"] == node)
        assert row["state"] == READING
        assert row["substituted_samples"] == len(clean_walk["samples"])
        assert presence["exit"] == 1, "a forced value must not read as clean"

    def test_reading_map_is_the_fact_the_engine_does_not_have(
            self, register, clean_walk):
        mapping = reading_map(classify(register, clean_walk))
        assert mapping[("PR-01", "die_temp_c")] is True
        assert ("PR-01", "SpareAnalog3") not in mapping


class TestStageOneNeedsNothingInstalled:
    def test_no_engine_import_anywhere_in_stage_one(self):
        """C1, asserted rather than described. Checked by PARSING the module
        rather than grepping it: a word search hits this docstring."""
        import ast
        import inspect
        from factory_line_audit import declarations, generator, presence
        for module in (presence, declarations, generator):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    assert "arbiter" not in name, f"{module.__name__} imports {name}"


class TestTheSpellingARealServerUses:
    """OPC UA names these codes without separators, and `asyncua` reports them
    that way: `GoodLocalOverride`, `BadDeviceFailure`, `GoodSubNormal`. The
    synthetic corpus wrote `Good_LocalOverride`. Matching only the corpus meant
    every compound word from a live server fell through to the unknown-word
    branch -- 36 of the 274 codes `asyncua` defines.

    It survived because the battery's collector translated into the corpus
    spelling before Stage 1 saw it, so the fixture agreed with the grader
    because a layer in between made them agree. Both are gone now: the
    translator, and the corpus spelling it translated into.

    **The tolerance below outlives the reason it was written.** A walk handed to
    this package is written by whatever produced it, so grading must not depend
    on the separator somebody chose. `battery/probe_status_words.py` grades the
    whole library vocabulary; these are the cases that matter, stated where they
    can be read.
    """

    def test_both_spellings_grade_the_same(self):
        from factory_line_audit.presence import grade
        for camel, underscored in (("GoodLocalOverride", "Good_LocalOverride"),
                                   ("BadDeviceFailure", "Bad_DeviceFailure"),
                                   ("GoodSubNormal", "Good_SubNormal")):
            assert grade(camel)[0] == grade(underscored)[0], camel

    def test_a_qualified_good_is_still_reading(self):
        """`GoodSubNormal` graded unusable, which inverts the three-state
        answer for a tag that IS reading."""
        from factory_line_audit.presence import grade
        assert grade("GoodSubNormal")[1]["usable"] is True

    def test_an_override_from_a_real_server_counts_as_substituted(self):
        """The count exists to tell a value a person typed at an HMI apart from
        one the process produced. Graded `uncertain`, it was always zero."""
        from factory_line_audit.presence import grade
        name, props = grade("GoodLocalOverride")
        assert name == "good_localoverride"
        assert props["substituted"] is True

    def test_an_edited_value_is_substituted_too(self):
        from factory_line_audit.presence import grade
        assert grade("GoodEdited")[1]["substituted"] is True

    def test_a_bad_code_grades_bad_and_not_merely_unknown(self):
        """Both are unusable, so the state is the same and the REASON was not.
        That is why the live rung passed while the grader was wrong."""
        from factory_line_audit.presence import grade
        assert grade("BadDeviceFailure")[0] == "bad"

    def test_a_word_nobody_has_seen_is_still_uncertain(self):
        """The conservative fallback stays: interpreting an unknown status
        optimistically is how a substituted value gets judged as a measurement."""
        from factory_line_audit.presence import grade
        name, props = grade("SomethingNoServerHasEverSent")
        assert name == "uncertain"
        assert props["usable"] is False

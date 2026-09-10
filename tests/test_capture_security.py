"""What `capture` refuses before it dials anything.

Every case here asserts the REFUSAL -- the reason, by its words -- and not
merely a non-zero exit. A flag accepted and then ignored is worse than one that
does not exist: the run reports having been taken with a protection nothing
applied, and the walk's provenance carries that claim downstream to a
certificate.

What is NOT here, stated so the gap is visible rather than inferred: a
successful secure connection. Nothing in this file opens a channel.

That paragraph used to end *so nothing in this repository can yet show that a
signed channel WORKS ... the battery cannot close it*, and both halves are now
false. `opcua_surface.py serve --certificate` serves
Basic256Sha256/SignAndEncrypt with a self-signed certificate, and the
`pin_channel` battery leg runs `capture` against it twice: a matching digest
walks and records the certificate the server actually presented, a wrong one
refuses naming both. So the claim *the library calls this hook* is measured
rather than grepped -- which matters, because every test below would pass if
`asyncua` never called it at all.

What is still out of reach, narrowly: a plant's PKI, a certificate anybody else
signed, and authentication. A self-signed certificate on loopback is evidence
about this package's plumbing, not about an engagement.
"""
from __future__ import annotations

import asyncio
import hashlib
import os

import pytest

from conftest import REGISTER
from factory_line_audit import formats
from factory_line_audit.capture import security_from_flags

LOOPBACK = "opc.tcp://127.0.0.1:4840/x"
#: RFC 5737 TEST-NET-1, which exists to be written down. A private
#: address here would be a plant address in a public repository, and
#: the hygiene gate refuses one -- which is how this line got written
#: the second time.
PLANT = "opc.tcp://192.0.2.10:4840/x"
#: A well-formed SHA-256 digest, at module scope because a comprehension in a
#: class body cannot see the class's own names.
GOOD_PIN = "ab" * 32
COLONED = ":".join(GOOD_PIN[i:i + 2] for i in range(0, 64, 2))


def refuse(**kwargs):
    base = dict(policy="None", mode="", cert=None, key=None, pin=None,
                insecure=False, endpoint=LOOPBACK)
    base.update(kwargs)
    with pytest.raises(formats.Refusal) as raised:
        security_from_flags(**base)
    return str(raised.value)


class TestCombinationsThatCannotBothBeTrue:
    def test_insecure_beside_a_pin(self):
        assert "opposite things" in refuse(insecure=True, pin="sha256:ab")

    def test_insecure_beside_a_policy(self):
        why = refuse(insecure=True, policy="Basic256Sha256",
                     cert="c.pem", key="k.pem")
        assert "shape of protection" in why

    def test_a_pin_with_nothing_to_check(self):
        """Nothing is exchanged under `None`, so the pin would reach the walk's
        provenance having verified nothing -- and a certificate downstream would
        read `pinned: true`."""
        assert "nothing to check" in refuse(pin="sha256:ab")

    def test_a_signing_mode_with_no_channel_to_sign(self):
        assert "no channel to sign" in refuse(mode="SignAndEncrypt")


class TestWhatASecurePolicyNeeds:
    def test_a_policy_without_a_client_certificate(self):
        assert "needs a client" in refuse(policy="Basic256Sha256")

    def test_a_policy_with_a_cert_and_no_key(self):
        assert "needs a client" in refuse(policy="Basic256Sha256", cert="c.pem")


class TestWithdrawnPolicies:
    @pytest.mark.parametrize("policy", ["Basic128Rsa15", "Basic256"])
    def test_they_are_not_offered(self, policy):
        """`asyncua` speaks both; the spec withdrew both. Offering a flag that
        looks like security and is not is the failure this family refuses."""
        assert "withdrawn" in refuse(policy=policy, cert="c.pem", key="k.pem")

    def test_and_they_are_absent_from_the_offer(self):
        pytest.importorskip("asyncua")
        from factory_line_audit.capture import offered_policies
        offered = offered_policies()
        assert "Basic128Rsa15" not in offered and "Basic256" not in offered
        assert "Basic256Sha256" in offered, offered


class TestUnencryptedOffLoopback:
    def test_it_is_refused_unless_asked_for_by_name(self):
        """Rung 3 is an anonymous localhost server and that is legitimate. The
        same connection to a plant address is a different act, and the walk has
        to be able to record that somebody chose it."""
        assert "loopback" in refuse(endpoint=PLANT)

    def test_insecure_says_somebody_chose_it(self):
        got = security_from_flags(policy="None", mode="", cert=None, key=None,
                                  pin=None, insecure=True, endpoint=PLANT)
        assert got["insecure"] is True
        assert got["security_policy"] == "None"

    def test_a_resolved_name_is_not_loopback(self):
        """`localhost` is whatever a resolver says it is. A walk taken over a
        resolved name is not evidence about the machine somebody meant."""
        assert "loopback" in refuse(endpoint="opc.tcp://localhost:4840/x")


class TestWhatItAccepts:
    """The non-vacuity control: every claim above is that something is refused,
    and a function that refused everything would satisfy all of them."""

    def test_anonymous_on_loopback(self):
        got = security_from_flags(policy="None", mode="", cert=None, key=None,
                                  pin=None, insecure=False, endpoint=LOOPBACK)
        assert got == {"security_policy": "None", "security_mode": "None",
                       "pinned": False, "insecure": False, "client_cert": False}

    def test_a_signed_and_encrypted_channel_with_a_pin(self):
        """A REAL digest. This read `pin="sha256:ab"` and asserted `pinned is
        True`, so the one test that accepted a pin accepted a two-character one
        -- the shape `normalise_pin` now refuses. The assertion was about the
        record, and the record was the thing that could not be wrong."""
        got = security_from_flags(policy="Basic256Sha256", mode="SignAndEncrypt",
                                  cert="c.pem", key="k.pem", pin="ab" * 32,
                                  insecure=False, endpoint=PLANT)
        assert got["pinned"] is True
        assert got["security_mode"] == "SignAndEncrypt"

    def test_a_policy_defaults_to_the_strongest_mode(self):
        """Choosing a policy and leaving the mode blank must not quietly mean
        `Sign` -- the weaker of the two that policy can do."""
        got = security_from_flags(policy="Aes256Sha256RsaPss", mode="",
                                  cert="c.pem", key="k.pem", pin=None,
                                  insecure=False, endpoint=PLANT)
        assert got["security_mode"] == "SignAndEncrypt"


class TestThePinIsCheckedAndNotJustRecorded:
    """S1 from the 0.1.6 review, and the severest thing in it.

    `--server-cert-pin-sha256` was refused in the two combinations that
    contradict it, recorded as `pinned: true` in the walk's provenance, and then
    never passed anywhere: `cmd_capture` did not hand it to `capture`, `_walk`
    had no parameter for it, and no line of code compared a certificate. The
    suite asserted `got["pinned"] is True` -- it pinned the record, not the
    behaviour. A walk could say it was taken over a pinned channel when nothing
    checked who answered.

    `asyncua` calls `Client.certificate_validator(cert, application)` with the
    server's certificate, so the pin is now that callable. These tests drive it
    directly with a real self-signed certificate: no server is needed to check
    that a digest comparison compares digests, and the rung-3 leg covers the
    channel.
    """

    @staticmethod
    def _certificate():
        """A real X.509, so the digest under test is a digest of a certificate.

        `cryptography` arrives with `asyncua`, which is the `[live]` extra -- and
        a pin can only be given to `capture`, which needs that extra, so skipping
        here skips nothing a `[detect]`-only install can reach. The no-skips job
        installs `[detect,live,vertical]`, so these run there for real.
        """
        pytest.importorskip("cryptography", reason="arrives with the [live] "
                                                   "extra, which is the only "
                                                   "way to reach a pin at all")
        import datetime as dt

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fla-test")])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(days=1))
                .not_valid_after(now + dt.timedelta(days=1))
                .sign(key, hashes.SHA256()))
        digest = hashlib.sha256(
            cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        return cert, digest

    def _run(self, pin, cert):
        from factory_line_audit.capture import _Pin
        checker = _Pin(pin, "opc.tcp://127.0.0.1:4840")
        asyncio.run(checker(cert))
        return checker

    def test_a_matching_pin_passes_and_records_what_it_compared(self):
        cert, digest = self._certificate()
        checker = self._run(digest, cert)
        assert checker.checked is True
        assert checker.digest == digest

    def test_a_wrong_pin_refuses_by_name_and_prints_both_digests(self):
        cert, digest = self._certificate()
        with pytest.raises(formats.Refusal) as caught:
            self._run("00" * 32, cert)
        assert digest in caught.value.message
        assert "does not match the pin" in caught.value.message

    def test_the_comparison_ignores_the_punctuation_a_person_pastes(self):
        """`openssl x509 -fingerprint -sha256` prints colons. A pin refused for
        its formatting reads exactly like a server that answered wrongly."""
        cert, digest = self._certificate()
        spaced = ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))
        assert self._run(spaced.upper(), cert).checked is True

    def test_a_second_certificate_does_not_match_the_first(self):
        """The control. If every certificate hashed to the same thing -- or the
        comparison were `in` rather than `==` -- both rules above would pass."""
        first, digest = self._certificate()
        other, _ = self._certificate()
        with pytest.raises(formats.Refusal):
            self._run(digest, other)

    def test_the_pin_reaches_the_walk_rather_than_stopping_at_the_flag(self):
        """The defect was a parameter that did not exist. Held against the
        signatures, because that is where it went missing."""
        import inspect

        from factory_line_audit import capture as module
        assert "pin" in inspect.signature(module.capture).parameters
        assert "pin" in inspect.signature(module._walk).parameters
        source = inspect.getsource(module._walk)
        assert "certificate_validator" in source
        assert "pinned.checked" in source, (
            "the walk does not assert the validator ran; a pin the library never "
            "calls would pass a wrong digest and still record itself")


class TestThePinIsAValidDigestBeforeAnythingIsDialled:
    """R2 from the 0.1.7 review. The flag was tested for truthiness only.

    `_Pin` stripped `:` and spaces, so `sha256:<hex>` -- the shape this
    package's own `digest()` prints over a file, and one hyphen away from what
    `openssl x509 -fingerprint -sha256` prints -- became a seventy-character
    string that could never equal a digest. The channel was refused, which is
    the safe direction, with a message saying the SERVER had presented the wrong
    certificate. A person reading that goes and looks at the plant.
    """

    def test_a_bare_digest_is_accepted(self):
        from factory_line_audit.capture import normalise_pin
        assert normalise_pin(GOOD_PIN) == GOOD_PIN

    @pytest.mark.parametrize("written", [
        "sha256:" + GOOD_PIN,
        "SHA256:" + GOOD_PIN,
        GOOD_PIN.upper(),
        COLONED,
        "SHA256 Fingerprint=" + COLONED.upper(),
        "  " + GOOD_PIN + "  ",
    ])
    def test_every_shape_a_person_pastes_reaches_the_same_digest(self, written):
        from factory_line_audit.capture import normalise_pin
        assert normalise_pin(written) == GOOD_PIN

    @pytest.mark.parametrize("bad", ["ab", "", "zz" * 32, GOOD_PIN + "ab", "sha256:"])
    def test_anything_that_is_not_a_digest_is_refused_by_name(self, bad):
        from factory_line_audit.capture import normalise_pin
        with pytest.raises(formats.Refusal) as caught:
            normalise_pin(bad)
        assert "not a SHA-256 certificate digest" in caught.value.message
        assert "Nothing was dialled" in caught.value.message

    def test_the_flag_check_refuses_it_too_rather_than_recording_pinned(self):
        """`security_from_flags` is where nothing has been dialled yet, and its
        return value is what claims `pinned`."""
        why = refuse(policy="Basic256Sha256", mode="SignAndEncrypt",
                     cert="c.pem", key="k.pem", pin="sha256:ab", endpoint=PLANT)
        assert "not a SHA-256 certificate digest" in why

    def test_a_contradiction_is_still_named_before_the_format(self):
        """Ordering, asserted. A reader told their digest is malformed when the
        real problem is `--insecure` beside it has been told the less useful of
        two true things."""
        assert "opposite things" in refuse(insecure=True, pin="sha256:ab")
        assert "nothing to check" in refuse(pin="sha256:ab")

    def test_the_checker_compares_the_normalised_value(self):
        """One normaliser, not two. A prefix handled in the flag check and not
        in the comparison would refuse the server instead of the flag."""
        from factory_line_audit.capture import _Pin
        assert _Pin("sha256:" + GOOD_PIN, LOOPBACK).expected == GOOD_PIN


class TestTheMembershipPassIsPinnedToo:
    """R1 from the 0.1.7 review. S1's fix covered the walk half only.

    `--membership-cache` dials the server first to ask which declared nodes are
    still in the address space. That pass took the security string, the
    credentials and the namespace, and not the pin -- so with both flags given
    the cheap dial happened on a channel whose peer was never checked. When it
    answered `unchanged` the verb printed `OUTCOME unchanged`, exited 0 and wrote
    NO WALK, and the walk is the only artifact that records `pinned`. The half of
    a verb that exits without writing evidence is the half nobody can audit.
    """

    def test_the_pin_reaches_the_membership_dial(self):
        import inspect

        from factory_line_audit import capture as module
        for name in ("membership", "_membership"):
            assert "pin" in inspect.signature(getattr(module, name)).parameters, name
        source = inspect.getsource(module._membership)
        assert "certificate_validator" in source
        assert "pinned.checked" in source, (
            "the membership pass does not assert the validator ran; a pin the "
            "library never calls would leave the cache trusted against nobody")

    def test_the_cli_hands_it_over(self):
        """The defect was an argument that was never passed, so the call site is
        where it is held -- read through the AST, because slicing the source on
        the next `)` finds the one closing `security_string(`, which is how this
        test first passed for the wrong reason."""
        import ast
        import inspect
        import textwrap

        from factory_line_audit import cli
        tree = ast.parse(textwrap.dedent(inspect.getsource(cli.cmd_capture)))
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "membership"]
        assert calls, "cmd_capture no longer dials membership at all"
        for call in calls:
            assert "pin" in [kw.arg for kw in call.keywords], \
                ast.dump(call)[:200]

    def test_the_record_says_what_it_was_taken_over(self):
        """A cache that cannot say whether it was pinned cannot be read against
        the channel that produced it."""
        import inspect
        source = inspect.getsource(
            __import__("factory_line_audit.capture", fromlist=["x"])._membership)
        assert '"pinned"' in source and '"server_cert_sha256"' in source


class TestACacheIsNotReusedAcrossAWeakerChannel:
    """The rule that falls out of R1: if the protection can lapse between two
    runs, the run that drops it is the one that skips the walk."""

    @staticmethod
    def _record(**over):
        base = {"endpoint": LOOPBACK, "present": ["a"], "absent": [],
                "namespaces": ["urn:x"], "pinned": False,
                "server_cert_sha256": None}
        base.update(over)
        return base

    def test_the_same_posture_is_unchanged(self):
        from factory_line_audit.capture import membership_unchanged
        assert membership_unchanged(self._record(), self._record()) is True

    def test_a_pinned_cache_is_not_reused_unpinned(self):
        from factory_line_audit.capture import membership_unchanged
        cached = self._record(pinned=True, server_cert_sha256=GOOD_PIN)
        assert membership_unchanged(cached, self._record()) is False

    def test_two_different_certificates_are_two_different_peers(self):
        from factory_line_audit.capture import membership_unchanged
        cached = self._record(pinned=True, server_cert_sha256=GOOD_PIN)
        fresh = self._record(pinned=True, server_cert_sha256="cd" * 32)
        assert membership_unchanged(cached, fresh) is False

    def test_adding_a_pin_to_an_unpinned_cache_is_allowed(self):
        """The direction that does not weaken anything: this run verified the
        peer, the cache did not, and the comparison is against a verified dial."""
        from factory_line_audit.capture import membership_unchanged
        fresh = self._record(pinned=True, server_cert_sha256=GOOD_PIN)
        assert membership_unchanged(self._record(), fresh) is True

    def test_a_0_1_7_cache_carries_neither_field_and_still_reads(self):
        """Backward compatibility, asserted rather than assumed."""
        from factory_line_audit.capture import membership_unchanged
        old = {"endpoint": LOOPBACK, "present": ["a"], "absent": [],
               "namespaces": ["urn:x"]}
        assert membership_unchanged(old, self._record()) is True


class TestTheCacheRecordsThePostureOfEveryPass:
    """N3 from the 0.1.8 review, and the hole the R1 fix left.

    The rule R1 landed -- a cache taken over a pinned channel is not reused over
    an unpinned one -- reads the two new fields out of the cache. The cache was
    written only when the membership had CHANGED, which is the one case where
    there is nothing to preserve. So a 0.1.7 cache on a plant whose address space
    is stable was never upgraded: the pinned run answered `unchanged` and
    returned before the write, the next unpinned run found no `pinned` to
    compare against, and the protection lapsed with nothing recording it.

    MEASURED against a server (0.1.8 review, Sec. 6 run 3) before it was fixed:
    step 3 left the cache without either field and step 4 exited 0. These tests
    drive `cmd_capture` with a stand-in for the client library, so they run in an
    interpreter with no `[live]` extra and no server -- the decision under test
    is the CLI's, not the library's.
    """

    RECORD = {"format": "factory-line-audit/membership/1",
              "endpoint": "opc.tcp://127.0.0.1:48499/x/",
              "checked_at": "2026-09-10T00:00:00+00:00",
              "namespaces": ["urn:x"], "present": ["ns=2;s=A"], "absent": []}
    #: Enough of a walk for the verb to report one. The shortcut cases must not
    #: reach it at all, and the case that SHOULD walk is asserted by the flag
    #: rather than by an exception: `cmd_capture` catches everything the dial
    #: raises, so a stand-in that raised would be reported as an unreachable
    #: server and the test would read as a pass.
    WALK = {"source": {"nodes_served": 1, "nodes_requested": 1,
                       "nodes_not_in_address_space": [],
                       "nodes_present_but_unreadable": [],
                       "security_policy": "Basic256Sha256",
                       "security_mode": "SignAndEncrypt", "pinned": False},
            "samples": []}

    @staticmethod
    def _run(monkeypatch, tmp_path, cache_body, *, pin, fresh):
        """`capture --membership-cache`, with the dial replaced.

        `sys.modules` carries a stand-in for `asyncua` so the verb's own `[live]`
        guard passes wherever this runs; nothing in it is called. A pin needs a
        policy to have anything to check, so the flags below are the ones a
        pinned run really carries.
        """
        import json
        import sys
        import types

        from factory_line_audit import capture as capture_module, cli
        monkeypatch.setitem(sys.modules, "asyncua",
                            types.ModuleType("asyncua"))
        dialled, walked = {}, []

        def fake_membership(register, endpoint, **kwargs):
            dialled.update(kwargs)
            return dict(fresh)

        def fake_capture(*args, **kwargs):
            walked.append(kwargs)
            return json.loads(json.dumps(TestTheCacheRecordsThePostureOfEveryPass.WALK))

        monkeypatch.setattr(capture_module, "membership", fake_membership)
        monkeypatch.setattr(capture_module, "capture", fake_capture)
        path = os.path.join(str(tmp_path), "membership.json")
        if cache_body is not None:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(cache_body, handle)
        material = {}
        for role in ("cert", "key"):
            material[role] = os.path.join(str(tmp_path), role + ".pem")
            with open(material[role], "w", encoding="utf-8") as handle:
                handle.write("not read by anything these tests call\n")
        argv = ["capture", "--register", REGISTER, "--target",
                "opc.tcp://127.0.0.1:48499/x/", "--out",
                os.path.join(str(tmp_path), "walk.json"),
                "--security-policy", "Basic256Sha256",
                "--security-mode", "SignAndEncrypt",
                "--cert", material["cert"], "--key", material["key"],
                "--membership-cache", path]
        if pin:
            argv += ["--server-cert-pin-sha256", pin]
        code = cli.main(argv)
        with open(path, encoding="utf-8") as handle:
            return code, json.load(handle), dialled, bool(walked)

    def test_an_unchanged_pinned_pass_upgrades_a_0_1_7_cache(self, monkeypatch,
                                                             tmp_path):
        fresh = dict(self.RECORD, pinned=True, server_cert_sha256=GOOD_PIN)
        code, written, dialled, walked = self._run(
            monkeypatch, tmp_path, dict(self.RECORD), pin=GOOD_PIN, fresh=fresh)
        assert code == 0, "the shortcut itself is still the right answer"
        assert not walked, "the membership was unchanged and a walk ran anyway"
        assert dialled.get("pin") == GOOD_PIN, "the pin never reached the dial"
        assert written.get("pinned") is True, (
            "the cache still does not record that it was taken over a pinned "
            "channel, so a later unpinned run has nothing to refuse")
        assert written.get("server_cert_sha256") == GOOD_PIN

    def test_the_upgraded_cache_then_refuses_an_unpinned_reuse(self, monkeypatch,
                                                               tmp_path):
        """The point of the upgrade, asserted end to end rather than inferred
        from the field being present."""
        from factory_line_audit.capture import membership_unchanged
        fresh = dict(self.RECORD, pinned=True, server_cert_sha256=GOOD_PIN)
        _, written, _, _ = self._run(monkeypatch, tmp_path, dict(self.RECORD),
                                     pin=GOOD_PIN, fresh=fresh)
        later = dict(self.RECORD, pinned=False, server_cert_sha256=None)
        assert membership_unchanged(written, later) is False, (
            "an unpinned run would reuse the upgraded cache and exit 0")

    def test_an_unpinned_pass_does_not_invent_a_posture(self, monkeypatch,
                                                        tmp_path):
        """The control. A write that always stamped `pinned` would satisfy the
        rule above and record a protection nothing applied."""
        fresh = dict(self.RECORD, pinned=False, server_cert_sha256=None)
        code, written, dialled, walked = self._run(
            monkeypatch, tmp_path, dict(self.RECORD), pin=None, fresh=fresh)
        assert code == 0
        assert not walked
        assert dialled.get("pin") is None
        assert written.get("pinned") is False
        assert written.get("server_cert_sha256") is None

    def test_a_pinned_cache_still_refuses_the_unpinned_run_outright(
            self, monkeypatch, tmp_path):
        """The other control: writing on every pass must not overwrite a STRONGER
        cached posture with a weaker one before anybody compares them. The
        comparison happens first, so this run WALKS rather than shortcutting,
        and the walk records the weaker posture where a reader can see it."""
        cached = dict(self.RECORD, pinned=True, server_cert_sha256=GOOD_PIN)
        fresh = dict(self.RECORD, pinned=False, server_cert_sha256=None)
        code, written, _, walked = self._run(monkeypatch, tmp_path, cached,
                                             pin=None, fresh=fresh)
        assert walked, (
            "the unpinned run reused a cache taken over a pinned channel; the "
            "protection lapsed and the walk that would have recorded it was "
            "never written")
        assert code == 0
        assert written.get("pinned") is False

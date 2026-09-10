"""What `capture` refuses before it dials anything.

Every case here asserts the REFUSAL -- the reason, by its words -- and not
merely a non-zero exit. A flag accepted and then ignored is worse than one that
does not exist: the run reports having been taken with a protection nothing
applied, and the walk's provenance carries that claim downstream to a
certificate.

What is NOT here, stated so the gap is visible rather than inferred: a
successful secure connection. The rung-3 surface is anonymous and has no PKI,
so nothing in this repository can yet show that a signed channel WORKS -- only
that the impossible combinations are refused. That is a real limit and the
battery cannot close it.
"""
from __future__ import annotations

import asyncio
import hashlib

import pytest

from factory_line_audit import formats
from factory_line_audit.capture import security_from_flags

LOOPBACK = "opc.tcp://127.0.0.1:4840/x"
#: RFC 5737 TEST-NET-1, which exists to be written down. A private
#: address here would be a plant address in a public repository, and
#: the hygiene gate refuses one -- which is how this line got written
#: the second time.
PLANT = "opc.tcp://192.0.2.10:4840/x"


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
        got = security_from_flags(policy="Basic256Sha256", mode="SignAndEncrypt",
                                  cert="c.pem", key="k.pem", pin="sha256:ab",
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

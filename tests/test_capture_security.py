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

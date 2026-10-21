"""Le scout ne va chercher que des adresses publiques, redirections comprises."""

import socket

import pytest
import requests

from agency_scout import core


def _resolve_to(address):
    return lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.1.1", "192.168.1.10", "169.254.169.254", "0.0.0.0"])
def test_un_nom_public_qui_pointe_vers_une_adresse_interne_est_refuse(monkeypatch, address):
    monkeypatch.setattr(core.socket, "getaddrinfo", _resolve_to(address))
    with pytest.raises(core.UnsafeHostError):
        core.assert_public_url("https://127.0.0.1.nip.io/")


def test_une_adresse_publique_est_acceptee(monkeypatch):
    monkeypatch.setattr(core.socket, "getaddrinfo", _resolve_to("93.184.215.14"))
    core.assert_public_url("https://exemple.fr/")


class _Response:
    def __init__(self, status, location=None):
        self.status_code = status
        self.headers = {"location": location} if location else {}
        self.is_redirect = location is not None


def test_une_redirection_vers_une_adresse_interne_est_refusee(monkeypatch):
    def resolve(host, port, *a, **k):
        ip = "93.184.215.14" if host == "exemple.fr" else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(core.socket, "getaddrinfo", resolve)

    class Client:
        def get(self, url, timeout, allow_redirects):
            assert allow_redirects is False
            return _Response(302, "http://interne.local:5678/") if "exemple.fr" in url else _Response(200)

    with pytest.raises(core.UnsafeHostError):
        core.safe_get(Client(), "https://exemple.fr/")


def test_trop_de_redirections(monkeypatch):
    monkeypatch.setattr(core.socket, "getaddrinfo", _resolve_to("93.184.215.14"))

    class Client:
        def get(self, url, timeout, allow_redirects):
            return _Response(301, "https://exemple.fr/boucle")

    with pytest.raises(requests.TooManyRedirects):
        core.safe_get(Client(), "https://exemple.fr/")

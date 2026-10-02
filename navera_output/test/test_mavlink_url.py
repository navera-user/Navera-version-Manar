"""Both serial forms and the network forms give the same connection arguments."""
import pytest

from navera_output.mavlink_url import parse


def test_serial_forms_are_equivalent():
    assert parse("serial:/dev/ttyTHS2:921600") == parse("/dev/ttyTHS2,921600") == ("/dev/ttyTHS2", 921600)


@pytest.mark.parametrize("url", ["udpin:0.0.0.0:14551", "udpout:127.0.0.1:14550", "tcp:127.0.0.1:5763"])
def test_network_urls_pass_through(url):
    assert parse(url) == (url, None)


@pytest.mark.parametrize("url", ["", "/dev/ttyTHS2", "serial:/dev/ttyTHS2", "ttyTHS2,57600", "serial:/dev/x:fast"])
def test_malformed_addresses_are_refused(url):
    with pytest.raises(ValueError):
        parse(url)

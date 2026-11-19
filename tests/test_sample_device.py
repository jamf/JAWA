"""Admins choose which device a Jamf Pro sample event names.

The bundled samples carry made-up ids (ComputerCheckIn has jssID 892).
A script that calls Jamf Pro with that id acts on whatever real device
has it, so the device fields are editable, remembered per automation,
and the full payload can be edited too.
"""

import html
import json

from bin.data_store import get_webhook_by_name, get_webhook_schemas
from tests.test_automations import (
    _SamplePopen,
    _fake_webhook_get,
    _jamf_automation,
)

URL = "/automations/jamfpro/GroupHook"


def _setup(jawa_env, monkeypatch, event="ComputerCheckIn"):
    import subprocess

    _SamplePopen.calls = []
    monkeypatch.setattr(subprocess, "Popen", _SamplePopen)
    _jamf_automation(jawa_env, event=event)
    _fake_webhook_get(monkeypatch, {"webhook": {"enabled": True}})
    return get_webhook_schemas()["examples"].get(event)


def _sent():
    assert len(_SamplePopen.calls) == 1
    return json.loads(_SamplePopen.calls[0][1])


def test_detail_prefills_device_fields_from_the_sample(
    logged_in_client, jawa_env, monkeypatch
):
    example = _setup(jawa_env, monkeypatch)
    body = logged_in_client.get(URL).data.decode()
    assert 'name="device_jssID"' in body
    assert f'value="{example["event"]["jssID"]}"' in body
    assert f'value="{example["event"]["serialNumber"]}"' in body
    assert 'name="device_udid"' in body
    assert 'name="device_deviceName"' in body
    assert "Edit full payload" in body


def test_sample_uses_the_device_the_admin_entered(
    logged_in_client, jawa_env, monkeypatch
):
    example = _setup(jawa_env, monkeypatch)
    logged_in_client.post(
        URL + "/test",
        data={
            "device_jssID": "1547",
            "device_serialNumber": "TESTSERIAL1",
            "device_udid": "",
            "device_deviceName": "Lab Mac",
        },
    )
    sent = _sent()
    assert sent["event"]["jssID"] == 1547
    assert sent["event"]["serialNumber"] == "TESTSERIAL1"
    assert sent["event"]["deviceName"] == "Lab Mac"
    # A blank field keeps the sample's value.
    assert sent["event"]["udid"] == example["event"]["udid"]
    # Everything else is the sample unchanged.
    assert sent["webhook"] == example["webhook"]
    assert sent["event"]["model"] == example["event"]["model"]


def test_the_device_is_remembered_for_next_time(
    logged_in_client, jawa_env, monkeypatch
):
    _setup(jawa_env, monkeypatch)
    logged_in_client.post(
        URL + "/test",
        data={"device_jssID": "1547", "device_serialNumber": "TESTSERIAL1"},
    )
    saved = get_webhook_by_name("GroupHook")["sample_device"]
    assert saved == {"jssID": 1547, "serialNumber": "TESTSERIAL1"}
    body = logged_in_client.get(URL).data.decode()
    assert 'value="1547"' in body
    assert 'value="TESTSERIAL1"' in body
    # The JSON view shows it too (escaped inside the textarea).
    assert '"jssID": 1547' in html.unescape(body)


def test_a_non_numeric_jamf_pro_id_is_refused(
    logged_in_client, jawa_env, monkeypatch
):
    _setup(jawa_env, monkeypatch)
    resp = logged_in_client.post(URL + "/test", data={"device_jssID": "abc"})
    assert "Jamf Pro ID must be a whole number" in resp.data.decode()
    assert _SamplePopen.calls == []
    assert "sample_device" not in get_webhook_by_name("GroupHook")


def test_an_edited_payload_is_sent_with_the_device_fields_on_top(
    logged_in_client, jawa_env, monkeypatch
):
    example = _setup(jawa_env, monkeypatch)
    edited = json.loads(json.dumps(example))
    edited["event"]["building"] = "Test Lab"
    edited["event"]["jssID"] = 5
    logged_in_client.post(
        URL + "/test",
        data={"payload": json.dumps(edited), "device_jssID": "1547"},
    )
    sent = _sent()
    assert sent["event"]["building"] == "Test Lab"
    assert sent["event"]["jssID"] == 1547


def test_an_edited_payload_must_be_a_json_object(
    logged_in_client, jawa_env, monkeypatch
):
    _setup(jawa_env, monkeypatch)
    for bad in ("{not json", "[1, 2]"):
        resp = logged_in_client.post(URL + "/test", data={"payload": bad})
        assert "Invalid JSON" in resp.data.decode()
    assert _SamplePopen.calls == []


def test_an_event_without_device_fields_shows_only_the_payload(
    logged_in_client, jawa_env, monkeypatch
):
    _setup(jawa_env, monkeypatch, event="JSSStartup")
    body = logged_in_client.get(URL).data.decode()
    assert 'name="device_' not in body
    assert "Edit full payload" in body

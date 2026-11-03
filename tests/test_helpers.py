"""Offline regression tests. Run: python3 -m unittest discover -s tests -v."""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '3x-ui-best-practices/scripts'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


validator = module('validate_config')
parser = module('parse_share_link')


def inbound(**kwargs):
    value = {'port': 443, 'protocol': 'vless',
             'settings': {'decryption': 'none', 'clients': [
                 {'email': 'test@example.test', 'flow': 'xtls-rprx-vision'}]},
             'streamSettings': {'network': 'tcp', 'security': 'tls'}}
    value.update(kwargs)
    return value


def check(value):
    return validator.run(json.dumps(value))


def cli(script, data, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), '-', *args],
                          input=data, capture_output=True, text=True)


class ValidatorTests(unittest.TestCase):
    def test_baseline_and_raw_alias(self):
        for network in ['tcp', 'raw']:
            self.assertEqual(check(inbound(streamSettings={'network': network, 'security': 'tls'})).error_count, 0)

    def test_legacy_json_objects(self):
        value = inbound()
        for key in ['settings', 'streamSettings']:
            value[key] = json.dumps(value[key])
        self.assertEqual(check(value).error_count, 0)

    def test_malformed_shapes_never_crash(self):
        for field in ['settings', 'streamSettings', 'sniffing']:
            for bad in [None, False, 1, [], ['secret'], 'not json', 'null', '[]']:
                with self.subTest(field=field, bad=bad):
                    self.assertGreater(check(inbound(**{field: bad})).error_count, 0)
        for bad in [False, [], {}, None, 42]:
            self.assertGreater(check(inbound(protocol=bad)).error_count, 0)
        for bad in [None, 1, False, {}, ['bad']]:
            self.assertGreater(check(inbound(settings={'clients': bad})).error_count, 0)
        for bad in [[], None, 1, 'bad']:
            self.assertGreater(check({'client': bad}).error_count, 0)
        for bad in [[], {}, 1, None]:
            self.assertGreater(check({'email': 'x', 'flow': bad}).error_count, 0)

    def test_nested_reality_and_sniff_types(self):
        for field in ['serverNames', 'shortIds']:
            for bad in [False, 12, {}, 'x', [[]]]:
                value = inbound(streamSettings={'security': 'reality', 'realitySettings': {field: bad}})
                self.assertGreater(check(value).error_count, 0)
        self.assertGreater(check(inbound(sniffing={'destOverride': [[]]})).error_count, 0)

    def test_bool_is_not_integer(self):
        self.assertGreater(check(inbound(port=True)).error_count, 0)
        for key in ['totalGB', 'expiryTime', 'limitIp']:
            self.assertGreater(check({'email': 'x', key: True}).error_count, 0)
        for ids in [[True], [0], [-1], ['1']]:
            self.assertGreater(check({'client': {'email': 'x'}, 'inboundIds': ids}).error_count, 0)

    def test_vision_protocol_and_transport(self):
        self.assertGreater(check(inbound(protocol='trojan')).error_count, 0)
        self.assertGreater(check(inbound(streamSettings={'network': 'ws', 'security': 'tls'})).error_count, 0)
        self.assertGreater(check(inbound(streamSettings={})).error_count, 0)

    def test_version_specific_modes_are_not_rewritten(self):
        value = inbound()
        value['settings']['decryption'] = 'replace-with-version-specific-encryption'
        report = check(value)
        self.assertEqual(report.error_count, 0)
        self.assertTrue(any(level == 'WARN' for level, _ in report.items))
        self.assertEqual(check({'email': 'x', 'expiryTime': -86400000}).error_count, 0)

    def test_short_ids(self):
        for sid, good in [('', True), ('ab12', True), ('ABCDEF0123456789', True),
                          ('a', False), ('xyz1', False), ('ab' * 9, False)]:
            value = inbound(streamSettings={'security': 'reality', 'realitySettings': {
                'serverNames': ['example.com'], 'shortIds': [sid]}})
            self.assertEqual(check(value).error_count == 0, good)

    def test_errors_do_not_echo_sensitive_values(self):
        sentinel = 'replace-with-private-sentinel'
        value = inbound(settings={'decryption': {'secret': sentinel}, 'clients': [
            {'email': sentinel, 'flow': sentinel}]})
        self.assertNotIn(sentinel, check(value).render())

    def test_exit_code_cannot_wrap_to_success(self):
        value = inbound(settings={'clients': [{} for _ in range(256)]})
        result = cli('validate_config.py', json.dumps(value))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback', result.stderr)

    def test_file_error_is_concise(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'validate_config.py'),
                                 '/nonexistent/input.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)


class ParserTests(unittest.TestCase):
    def test_trojan_colon_password_and_ipv6(self):
        value = parser.parse_link('trojan://replace-with%3Apassword@[2001:db8::1]:443', True)
        self.assertEqual(value['password'], 'replace-with:password')
        self.assertEqual(value['address'], '2001:db8::1')

    def test_redaction_and_explicit_reveal(self):
        sentinel = 'replace-with-private-sentinel'
        link = f'trojan://{sentinel}@example.com:443?path=/{sentinel}&token={sentinel}&security=tls#{sentinel}'
        self.assertNotIn(sentinel, json.dumps(parser.parse_link(link)))
        self.assertEqual(parser.parse_link(link, True)['password'], sentinel)
        self.assertEqual(parser.parse_link(link)['params']['security'], 'tls')

    def test_bad_links_fail_without_leaking(self):
        links = ['vless://secret@example.com:secret', 'vless://@example.com:443',
                 'vless://secret@example.com', 'vless://secret@example.com:65536',
                 'vless://secret@example.com:0', 'vless://secret@example.com:443?type=tcp&type=ws',
                 'trojan://secret@[bad]:443', 'vmess://!!!']
        for value in [[], None, {'id': 'secret', 'add': 'example.com', 'port': []},
                      {'id': 'secret', 'add': 'example.com', 'port': True},
                      {'id': 'secret', 'add': 'example.com', 'port': 443, 'path': {}}]:
            links.append('vmess://' + base64.b64encode(json.dumps(value).encode()).decode())
        for link in links:
            with self.subTest(link=link):
                result = cli('parse_share_link.py', link)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('secret', result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_unpadded_base64url(self):
        data = {'id': 'replace-with-id', 'add': 'example.com', 'port': '443', 'net': 'ws'}
        link = 'vmess://' + base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
        self.assertEqual(parser.parse_link(link)['port'], 443)


if __name__ == '__main__':
    unittest.main()

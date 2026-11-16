"""Offline contract tests; no Docker, AWS, kubectl or network connection required."""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


metrics = load('scripts/data_collection/collect_metrics_prometheus.py', 'metrics')
stress = load('scripts/fault_injection/inject_cpu_stress.py', 'stress')


def vector(label, values):
    return [{'metric': {label: k}, 'value': [0, str(v)]} for k, v in values.items()]


def mocked_queries(prometheus, expression):
    if 'http_requests_total{status=' in expression:
        return vector('job', {'order-service': 0.5})
    if 'http_requests_total' in expression:
        return vector('job', {'api-gateway': 2, 'order-service': 1, 'payment-service': 1})
    if 'histogram_quantile' in expression:
        return vector('job', {'api-gateway': .02, 'order-service': .1, 'payment-service': .04})
    if 'container_cpu_usage_seconds_total' in expression:
        assert 'namespace="microservices"' in expression
        return vector('container', {'api-gateway': 12, 'order-service': 47.3, 'payment-service': 8})
    if 'container_memory_working_set_bytes' in expression:
        return vector('container', {'api-gateway': 48, 'order-service': 126, 'payment-service': 51})
    raise AssertionError('Unexpected PromQL: ' + expression)


class CollectorTests(unittest.TestCase):
    def test_separate_file_defaults(self):
        self.assertEqual(metrics.parse_args([]).output, 'dataset/a3_metrics_clean_local.csv')
        self.assertEqual(metrics.parse_args(['--environment', 'eks']).output, 'dataset/a3_metrics_clean_eks.csv')

    def test_parse_docker_memory(self):
        self.assertAlmostEqual(metrics.parse_memory_mib('63.63MiB / 4GiB'), 63.63)
        self.assertAlmostEqual(metrics.parse_memory_mib('1.25GiB / 4GiB'), 1280)
        self.assertAlmostEqual(metrics.parse_memory_mib('1024KiB / 4GiB'), 1)
        with self.assertRaises(ValueError):
            metrics.parse_memory_mib('bad')

    def test_local_docker_stats(self):
        stdout = 'microservices-api-gateway-1,0.22%,43.4MiB / 2GiB\nmicroservices-order-service-1,200.94%,63.63MiB / 2GiB\nmicroservices-payment-service-1,0.11%,67.1MiB / 2GiB\n'
        with mock.patch.object(metrics.subprocess, 'check_output', return_value=stdout) as process:
            values = metrics.local_resources()
        self.assertEqual(values['order-service'], (200.94, 63.63))
        process.assert_called_once()

    def test_eks_metrics_are_by_exact_container_not_docker(self):
        def queries(url, expr):
            if 'container_cpu_usage_seconds_total' in expr:
                return vector('container', {'api-gateway': 10, 'order-service': 49.9, 'payment-service': 4})
            return vector('container', {'api-gateway': 40, 'order-service': 128.1, 'payment-service': 39})
        with mock.patch.object(metrics, 'query_prometheus', side_effect=queries):
            values = metrics.eks_resources('http://localhost:9090', 'microservices')
        self.assertEqual(values['order-service'], (49.9, 128.1))

    def test_eks_snapshot_label_and_units(self):
        args = metrics.parse_args(['--environment', 'eks', '--fault', 'cpu_stress', '--check'])
        with mock.patch.object(metrics, 'query_prometheus', side_effect=mocked_queries):
            row = metrics.snapshot(args)
        self.assertEqual(row['fault_type'], 'cpu_stress')
        self.assertEqual(row['order_cpu'], 47.3)
        self.assertEqual(row['order_mem'], 126)
        self.assertEqual(row['order_p95_latency'], 100)
        self.assertEqual(row['order_error_rate'], .5)
        self.assertEqual(row['gw_error_rate'], 0)
        self.assertEqual(row['db_query_latency_p95'], '')

    def test_missing_container_metrics_fails_before_writing(self):
        args = metrics.parse_args(['--environment', 'eks'])
        with mock.patch.object(metrics, 'query_prometheus', side_effect=mocked_queries), \
                mock.patch.object(metrics, 'eks_resources', return_value={'api-gateway': (1, 2), 'order-service': None, 'payment-service': (1, 2)}):
            with self.assertRaisesRegex(RuntimeError, 'No EKS CPU/RAM series'):
                metrics.snapshot(args)

    def test_missing_http_metrics_fails(self):
        args = metrics.parse_args(['--environment', 'eks'])
        def only_resources(url, expr):
            if 'container_cpu_usage_seconds_total' in expr:
                return vector('container', {k: 1 for k in metrics.SERVICES})
            if 'container_memory_working_set_bytes' in expr:
                return vector('container', {k: 10 for k in metrics.SERVICES})
            return []
        with mock.patch.object(metrics, 'query_prometheus', side_effect=only_resources):
            with self.assertRaisesRegex(RuntimeError, 'Missing HTTP request-rate'):
                metrics.snapshot(args)

    def test_csv_write_and_schema_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            output = str(Path(temp) / 'dataset' / 'metrics.csv')
            row = {field: '' for field in metrics.FIELDS}
            row.update({'timestamp': '2026-11-17T00:00:00+00:00', 'fault_type': 'normal', 'order_cpu': 0.05})
            metrics.append_row(output, row)
            metrics.append_row(output, row)
            with open(output, newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['order_cpu'], '0.05')
            with open(output, 'w') as f:
                f.write('other,header\n')
            with self.assertRaisesRegex(RuntimeError, 'Refusing to append'):
                metrics.append_row(output, row)


READY = {
    'metadata': {'name': 'order-service-788f774-abc', 'labels': {'app': 'order-service'}},
    'status': {'phase': 'Running', 'containerStatuses': [{'name': 'order-service', 'ready': True}]}
}


class InjectionTests(unittest.TestCase):
    def test_select_ready_pod(self):
        not_ready = {
            'metadata': {'name': 'order-service-788f774-z', 'labels': {'app': 'order-service'}},
            'status': {'phase': 'Running', 'containerStatuses': [{'name': 'order-service', 'ready': False}]}
        }
        self.assertEqual(stress.select_ready_pod([not_ready, READY], 'order-service'), READY['metadata']['name'])
        with self.assertRaisesRegex(RuntimeError, 'No Ready running pod'):
            stress.select_ready_pod([not_ready], 'order-service')

    def test_kubectl_exec_correct_command(self):
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            if command[1] == 'get':
                return SimpleNamespace(stdout=json.dumps({'items': [READY]}))
            return SimpleNamespace(stdout='')
        with mock.patch.object(stress, 'run_cmd', side_effect=fake_run):
            status = stress.main(['--service', 'order-service', '--duration', '1', '--workers', '1'])
        self.assertEqual(status, 0)
        self.assertEqual(calls[0][0:4], ['kubectl', 'get', 'pods', '-n'])
        self.assertEqual(calls[1][0:8], ['kubectl', 'exec', '-n', 'microservices', READY['metadata']['name'], '-c', 'order-service', '--'])
        self.assertEqual(calls[1][-2:], ['1', '1'])
        self.assertNotIn('python3 -c', str(calls[1]))

    def test_failure_does_not_print_ok_or_return_success(self):
        with mock.patch.object(stress, 'run_cmd', side_effect=FileNotFoundError('kubectl')):
            self.assertEqual(stress.main(['--duration', '1']), 1)

    @unittest.skipIf(sys.platform.startswith('win') or shutil.which('sh') is None,
                     'POSIX shell stress test is skipped on Windows (requires sh)')
    def test_shell_bounded_stress_finishes(self):
        start = time.monotonic()
        proc = subprocess.run(['sh', '-c', stress.STRESS_SH, 'sh', '1', '1'], timeout=8, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertLess(time.monotonic() - start, 7)


if __name__ == '__main__':
    unittest.main()

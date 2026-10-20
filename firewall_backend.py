#!/usr/bin/python3 -I
"""Standalone, installable firewall broker. Only fixed report/enable/disable operations.

Copy this single file to a root-owned location; never sudo-import project code.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

TOOLS = {'ufw': 'UFW', 'firewalld': 'firewalld', 'nftables': 'nftables', 'iptables': 'iptables'}
COMMANDS = {'ufw': 'ufw', 'firewalld': 'firewall-cmd', 'nftables': 'nft', 'iptables': 'iptables'}


def executable(name):
    # Never use a web/service user's PATH for privileged command discovery.
    return shutil.which(name, path='/usr/sbin:/usr/bin:/sbin:/bin')


def run(args, timeout=5):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors='replace', timeout=timeout, check=False,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if len(result.stdout) > 524288:
        raise ValueError('Firewall report exceeds the supported size.')
    return result.returncode, result.stdout.strip()


def ufw_rules(text):
    rules = []
    for line in text.splitlines():
        match = re.match(r'^(.+?)\s{2,}(ALLOW|DENY|REJECT|LIMIT)(?:\s+(IN|OUT|FWD))?\s{2,}(.+)$', line.strip())
        if match:
            target, action, direction, source = match.groups()
            rules.append(dict(action=action.lower(), direction=(direction or 'IN').lower(),
                              target=target.strip(), source=source.strip(), details='', scope='live'))
    return rules


def defaults(text):
    match = re.search(r'^Default:\s*(.+)$', text, re.M)
    if not match:
        return []
    return [dict(direction=direction, action=action.strip()) for action, direction in
            re.findall(r'([^,]+?)\s*\((incoming|outgoing|routed)\)', match[1])]


def ufw_report(path):
    code, raw = run([path, 'status', 'verbose'])
    if code or not re.search(r'^Status: (active|inactive)$', raw, re.M):
        return dict(active=None, raw='', rules=[], policies=[], error='Administrator access is required to inspect UFW status and rules.')
    active = bool(re.search(r'^Status: active$', raw, re.M))
    rules = ufw_rules(raw)
    policies = defaults(raw)
    if not active:
        added_code, added = run([path, 'show', 'added'])
        if added_code == 0:
            raw += '\n\nSaved rules (not currently enforced by UFW):\n' + added
            for line in added.splitlines():
                match = re.match(r'^ufw\s+(?:route\s+)?(allow|deny|reject|limit)\s+(.+)$', line)
                if match:
                    rules.append(dict(action=match[1], direction='configured', target=match[2], source='See rule', details=line, scope='saved'))
    return dict(active=active, raw=raw, rules=rules, policies=policies, error=None)


def firewalld_report(path):
    code, state = run([path, '--state'])
    if state == 'not running':
        return dict(active=False, raw=state, rules=[], policies=[], error=None)
    if code or state != 'running':
        return dict(active=None, raw='', rules=[], policies=[], error='Unable to query firewalld. Check permissions and the system bus.')
    # Only active zones are reported as live; inactive zone definitions are not enforced.
    code, zones_text = run([path, '--get-active-zones'])
    if code:
        return dict(active=True, raw=state, rules=[], policies=[], error='firewalld is running, but its active zones could not be read.')
    zones = [line.split()[0] for line in zones_text.splitlines() if line and not line[0].isspace()]
    raw_parts = ['Active zones:\n' + zones_text]
    rules, policies = [], []
    errors = []
    for zone in zones:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', zone):
            errors.append('An active zone has an unsupported name.')
            continue
        code, detail = run([path, '--zone=' + zone, '--list-all'])
        if code:
            errors.append('Could not inspect active zone ' + zone + '.')
            continue
        raw_parts.append(detail)
        fields = dict(re.findall(r'^\s+([\w-]+):\s*(.*)$', detail, re.M))
        policies.append(dict(direction=zone, action=fields.get('target', 'unknown')))
        for field, action in [('services', 'allow'), ('ports', 'allow'), ('source-ports', 'allow'), ('icmp-blocks', 'block')]:
            if field == 'icmp-blocks' and fields.get('icmp-block-inversion') == 'yes':
                action = 'allow'
            for value in fields.get(field, '').split():
                rules.append(dict(action=action, direction='zone: ' + zone, target=value, source=field,
                                  details='Zone applies to its listed interfaces/sources.', scope='live'))
        rich = False
        for line in detail.splitlines():
            if line.strip() == 'rich rules:':
                rich = True
            elif rich and line.strip():
                action = 'allow' if re.search(r'\baccept\b', line) else 'block' if re.search(r'\b(drop|reject)\b', line) else 'other'
                rules.append(dict(action=action, direction='zone: ' + zone, target='Rich rule', source='Custom', details=line.strip(), scope='live'))
    # Preserve policy objects, including restrictions beyond active zone listings.
    policy_code, policy_names = run([path, '--get-active-policies'])
    if policy_code:
        errors.append('Active policy objects could not be read; report may be incomplete.')
    else:
        for name in policy_names.split():
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
                continue
            code, detail = run([path, '--info-policy=' + name])
            if code:
                errors.append('Could not read policy ' + name + '.')
            else:
                raw_parts.append('Active policy:\n' + detail)
    return dict(active=True, raw='\n\n'.join(raw_parts), rules=rules, policies=policies,
                error=' '.join(errors) or None)


def low_level_report(backend, path):
    rules, policies = [], []
    if backend == 'nftables':
        code, raw = run([path, '-j', 'list', 'ruleset'])
        if code:
            raise PermissionError('Administrator access is required to read nftables rules.')
        objects = json.loads(raw).get('nftables', [])
        filtering = []
        for obj in objects:
            if 'chain' in obj:
                chain = obj['chain']
                if chain.get('type') == 'filter' and chain.get('hook'):
                    filtering.append(chain)
                    policies.append(dict(direction='/'.join(str(chain.get(k, '')) for k in ('family', 'table', 'name')), action=chain.get('policy', 'unspecified')))
            if 'rule' in obj:
                rule = obj['rule']
                expr = rule.get('expr', [])
                action = next((key for item in expr for key in item if key in ('accept', 'drop', 'reject')), 'other')
                rules.append(dict(action=action, direction=rule.get('chain', ''), target=rule.get('table', ''), source=rule.get('family', ''), details=json.dumps(expr), scope='live'))
        return dict(active=bool(filtering), raw=json.dumps(json.loads(raw), indent=2), rules=rules, policies=policies, error=None)
    parts = []
    # Include both address families; never present IPv4-only output as complete.
    for name in ('iptables', 'ip6tables'):
        binary = executable(name)
        if not binary:
            return dict(active=None, raw='\n'.join(parts), rules=rules, policies=policies, error='Both IPv4 and IPv6 iptables tools are required for a complete report.')
        code, raw = run([binary, '-S'])
        if code:
            raise PermissionError('Administrator access is required to read iptables rules.')
        parts.append(name + ':\n' + raw)
        for line in raw.splitlines():
            policy = re.match(r'^-P (\S+) (\S+)$', line)
            if policy:
                policies.append(dict(direction=name + '/' + policy[1], action=policy[2].lower()))
            elif line.startswith('-A '):
                action = re.search(r'\s-j (ACCEPT|DROP|REJECT)\b', line)
                rules.append(dict(action=action[1].lower() if action else 'other', direction=name + '/' + line.split()[1], target='Filter rule', source='See rule', details=line, scope='live'))
    active = bool(rules) or any(p['action'] != 'accept' for p in policies)
    return dict(active=active, raw='\n\n'.join(parts), rules=rules, policies=policies, error=None)


def revision(report):
    fields = {key: report.get(key) for key in ('backend', 'active', 'raw', 'installed', 'detected_managers', 'can_toggle')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def report():
    found = {name: executable(command) for name, command in COMMANDS.items()}
    installed = [name for name, path in found.items() if path]
    reports = {}
    for name in ('ufw', 'firewalld'):
        if found[name]:
            try:
                reports[name] = ufw_report(found[name]) if name == 'ufw' else firewalld_report(found[name])
            except (OSError, ValueError, subprocess.TimeoutExpired):
                reports[name] = dict(active=None, raw='', rules=[], policies=[], error='Firewall inspection failed or timed out.')
    active_managers = [name for name, item in reports.items() if item['active'] is True]
    backend = active_managers[0] if active_managers else next(iter(reports), None)
    if backend is None:
        for name in ('nftables', 'iptables'):
            if found[name]:
                try:
                    reports[name] = low_level_report(name, found[name])
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    reports[name] = dict(active=None, raw='', rules=[], policies=[], error='Administrator access is required to inspect the kernel firewall.')
        backend = next((name for name, item in reports.items() if item['active'] is True), next(iter(reports), None))
    result = dict(backend=backend, name=TOOLS.get(backend, 'Not detected'), installed=installed,
                  sampled_at=int(time.time()), conflict=len(active_managers) > 1,
                  scope='Rules reported by the selected manager; other kernel chains, containers, routers and cloud firewalls may also affect traffic.')
    result.update(reports.get(backend, dict(active=None, raw='', rules=[], policies=[], error='No supported firewall tool was found.')))
    # An unknown second manager can be active: do not switch blindly.
    uncertain = any(name != backend and item['active'] is None for name, item in reports.items())
    result['detected_managers'] = [dict(backend=name, active=item['active']) for name, item in reports.items()]
    result['can_toggle'] = backend in ('ufw', 'firewalld') and result['active'] is not None and not result['conflict'] and not uncertain and not result['error']
    if result['conflict']:
        result['error'] = 'Multiple firewall managers are active. Resolve the conflict before switching.'
    elif uncertain:
        result['error'] = 'Another installed firewall manager could not be inspected. Switching is unavailable.'
    if backend == 'firewalld':
        try:
            config = Path('/etc/firewalld/firewalld.conf').read_text()
        except FileNotFoundError:
            config = ''
        except OSError:
            config = 'CleanupOnExit=no'
        if re.search(r'^\s*CleanupOnExit\s*=\s*no\s*$', config, re.M | re.I):
            result['can_toggle'] = False
            result['error'] = 'firewalld cleanup on exit is disabled or unreadable; stopping its service may leave rules installed. Switching is unavailable.'
    if backend in ('nftables', 'iptables'):
        result['scope'] = 'Read-only kernel rule report. Raw rulesets cannot be safely disabled/re-enabled by this version. iptables reports the filter table only; nftables reports all visible tables.'
    result['revision'] = revision(result)
    return result


def set_enabled(backend, enabled, expected):
    current = report()
    if current['backend'] != backend or current['revision'] != expected:
        return dict(error='Firewall state changed. Refresh the report before switching.', code='conflict'), 409
    if not current['can_toggle']:
        return dict(error='This firewall cannot be switched safely with the current report.', code='unsupported'), 409
    if current['active'] == enabled:
        return current, 200
    if backend == 'ufw':
        command = [executable('ufw'), '--force', 'enable' if enabled else 'disable']
    elif backend == 'firewalld':
        systemctl = executable('systemctl')
        if not systemctl:
            return dict(error='systemctl is required to switch firewalld.', code='unsupported'), 409
        command = [systemctl, 'start' if enabled else 'stop', 'firewalld.service']
    else:
        return dict(error='Unsupported firewall manager.', code='unsupported'), 409
    try:
        code, _ = run(command, timeout=20)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return dict(error='Firewall change could not be confirmed. Refresh before trying again.', code='uncertain'), 503
    updated = report()
    selected = ufw_report(executable('ufw')) if backend == 'ufw' else firewalld_report(executable('firewall-cmd'))
    if code or selected['active'] != enabled:
        return dict(error='The requested firewall state was not confirmed. Refresh the report.', code='uncertain', report=updated), 503
    return updated, 200


def main():
    args = sys.argv[1:]
    if args != ['report'] and not (len(args) == 4 and args[0] == 'set' and args[1] in ('ufw', 'firewalld') and args[2] in ('on', 'off') and re.fullmatch('[a-f0-9]{64}', args[3])):
        print(json.dumps(dict(error='Unsupported helper arguments.', status=400)))
        return 1
    if os.geteuid() != 0:
        print(json.dumps(dict(error='The installed helper requires administrator privileges.', status=403)))
        return 1
    # /run is root-owned. Serialize operations across separate sudo invocations.
    with open('/run/driftos-firewall.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps(dict(error='A firewall operation is in progress. Refresh shortly.', status=409)))
            return 1
        try:
            data, status = (report(), 200) if args == ['report'] else set_enabled(args[1], args[2] == 'on', args[3])
        except (OSError, ValueError, subprocess.TimeoutExpired):
            data, status = dict(error='Firewall inspection failed. Check the host configuration.'), 503
        print(json.dumps(dict(status=status, data=data)))
        return 0 if status == 200 else 1


if __name__ == '__main__':
    raise SystemExit(main())

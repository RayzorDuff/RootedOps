#!/usr/bin/env python3
"""Run on the Mac with the existing directory-venv and SSH access to Linode.
Preview by default. No secrets or identifiers printed. Existing directors only.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

def run(argv, data=None):
    return subprocess.run(argv, input=data, text=True, capture_output=True, check=True).stdout

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ssh", required=True, help="SSH destination for production Linode")
    p.add_argument("--workspace-email", required=True)
    p.add_argument("--wordpress-user", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.@:-]+", a.ssh) or a.ssh.startswith("-"):
        p.error("Invalid SSH destination")
    base = Path.home() / ".config/rootedops"
    scripts = Path(__file__).resolve().parent
    def remote(container, env, argv, source):
        # Transfer private identifiers over SSH stdin, not remote process arguments.
        # sudo normally strips environment variables; inject values inside
        # the container's interpreter via its private stdin instead.
        cmd = ["sudo", "-n", "docker", "exec", "-i", container] + argv
        if container == ak:
            source = "import os\n" + "\n".join("os.environ[" + repr(k) + "] = " + repr(str(v)) for k,v in env.items()) + "\n" + source
        else:
            import base64
            prefix = "\n".join("putenv(base64_decode('" + base64.b64encode((k+"="+str(v)).encode()).decode() + "'));" for k,v in env.items())
            source = source.replace("<?php", "<?php\n"+prefix+"\n", 1)
        return run(["ssh", "-T", a.ssh, shlex.join(cmd)], source)
    wp = "docker-rootedpsyche-wordpress-1"
    ak = "authentik-server"
    wp_code = (scripts/"wordpress_auth_subject_link.php").read_text()
    ak_code = (scripts/"authentik_workspace_preprovision.py").read_text()
    target = {"ROOTEDOPS_WP_USERNAME": a.wordpress_user,
              "ROOTEDOPS_APPROVED_WORKSPACE_EMAIL": a.workspace_email.strip().lower()}
    def wp_call(extra):
        return remote(wp, {**target, **extra}, ["php"], wp_code)
    if "TARGET_OK" not in wp_call({"ROOTEDOPS_TARGET_PREFLIGHT":"YES"}):
        raise RuntimeError("WordPress target preflight failed")
    directory = run([os.sys.executable, str(scripts/"workspace_directory_lookup.py"),
        "--credentials", str(base/"rootedpsyche-directory-client.json"),
        "--token", str(base/"rootedpsyche-directory-token.json"),
        "--domain", "rootedpsyche.org", "--control-email", "admin@rootedpsyche.org",
        "--workspace-email", a.workspace_email])
    record = json.loads(directory.splitlines()[-1])
    env = {"ROOTEDOPS_WORKSPACE_EMAIL": record["workspace_email"],
           "ROOTEDOPS_GOOGLE_IDENTIFIER": record["google_identifier"],
           "ROOTEDOPS_CONTROL_EMAIL": record["control_email"],
           "ROOTEDOPS_CONTROL_GOOGLE_IDENTIFIER": record["control_identifier"],
           "ROOTEDOPS_DISPLAY_NAME": record["display_name"]}
    def identity(apply):
        output = remote(ak, {**env, "ROOTEDOPS_APPLY": "YES" if apply else "NO"},
                        ["ak","shell","-c",'exec(__import__("sys").stdin.read())'], ak_code)
        lines = [line for line in output.splitlines() if line.startswith("ROOTEDOPS_RESULT=")]
        if len(lines) != 1:
            raise RuntimeError("No unique authentik receipt")
        result = json.loads(lines[0].split("=",1)[1])
        if result["applied"] is not apply:
            raise RuntimeError("Unexpected authentik receipt")
        return result
    preview = identity(False)
    if preview["subject"]:
        wp_call({"ROOTEDOPS_OIDC_SUB": preview["subject"]})
    print("Preview passed: directory and existing WordPress director checked; identity state:", preview["state"])
    if not a.apply:
        print("No account changes. New identity subject collision check runs after creation, before WordPress registration.")
        return
    receipt = identity(True)
    subject = receipt["subject"]
    if not isinstance(subject,str) or not re.fullmatch(r"[a-f0-9]{64}",subject):
        raise RuntimeError("Unexpected authentik subject; stop and reconcile")
    wp_call({"ROOTEDOPS_OIDC_SUB":subject})
    if "LINK_OK" not in wp_call({"ROOTEDOPS_OIDC_SUB":subject,"ROOTEDOPS_APPLY":"YES","ROOTEDOPS_REGISTER_MANAGED":"YES"}):
        raise RuntimeError("WordPress registration incomplete; rerun after reconciliation")
    print("Provisioned existing director. First Workspace sign-in required; no verification fabricated.")

if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, ValueError, RuntimeError, OSError, KeyError):
        raise SystemExit("Provisioning stopped; no automatic rollback. Inspect target privately and rerun preview. Check SSH sudo -n access and OAuth credentials.")

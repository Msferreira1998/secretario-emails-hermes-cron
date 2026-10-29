"""Instalação idempotente no Hermes: scripts, skill, cron 07:30 e alerta a cada 15 min; remove a triagem antiga."""
import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NOME = "Secretário de e-mails"
ALERTA = "Alerta de e-mails"


def _hermes(*args):
    r = subprocess.run(["hermes", *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"hermes {' '.join(args[:2])} falhou: {r.stderr.strip()[:200]}")
    return r.stdout


def jobs():
    blocos = re.split(r"\n(?=\s+[0-9a-f]{12} \[)", _hermes("cron", "list"))
    out = []
    for b in blocos:
        m = re.search(r"^\s+([0-9a-f]{12}) \[", b, re.M)
        if not m:
            continue
        nome = re.search(r"Name:\s+(.+)", b)
        skills = re.search(r"Skills:\s+(.+)", b)
        out.append({"id": m.group(1), "nome": nome.group(1).strip() if nome else "",
                    "skills": [s.strip() for s in skills.group(1).split(",")] if skills else []})
    return out


def instalar():
    home = Path.home()
    script = home / ".hermes/scripts/secretario.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text((RAIZ / "scripts/secretario.sh").read_text().replace("{{RAIZ}}", str(RAIZ)))
    script.chmod(0o755)
    alerta = script.with_name("secretario-alerta.sh")
    alerta.write_text((RAIZ / "scripts/secretario-alerta.sh").read_text().replace("{{RAIZ}}", str(RAIZ)))
    alerta.chmod(0o755)
    skill = home / ".hermes/skills/productivity/secretario-emails/SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text((RAIZ / "hermes-skill/secretario-emails/SKILL.md").read_text().replace("{{RAIZ}}", str(RAIZ)))
    feito = [f"script em {script}", f"skill em {skill}"]
    for j in jobs():
        if j["nome"] == "Triagem de e-mails":
            _hermes("cron", "remove", j["id"])
            feito.append(f"triagem antiga {j['id']} removida")
        elif j["nome"] == "Revisão semanal" and "himalaya" in j["skills"]:
            _hermes("cron", "edit", j["id"], "--remove-skill", "himalaya")
            feito.append("revisão semanal sem leitura de e-mails")
    if not any(j["nome"] == NOME for j in jobs()):
        _hermes("cron", "create", "30 7 * * *", "--name", NOME, "--no-agent", "--script", "secretario.sh",
                "--deliver", "telegram")
        feito.append("cron 30 7 * * * criado")
    if not any(j["nome"] == ALERTA for j in jobs()):
        # falha a cada 15 min não vira mensagem: o erro vai para o log e a faxina diária mostra a conta com problema
        _hermes("cron", "create", "*/15 * * * *", "--name", ALERTA, "--no-agent", "--script", "secretario-alerta.sh",
                "--deliver", "telegram", "--failure-deliver", "local")
        feito.append("alerta */15 criado")
    print("✅ Secretário instalado: " + "; ".join(feito) + ".")
    return 0

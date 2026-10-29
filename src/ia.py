"""Chamada à IA do Hermes para classificar o que as regras não resolvem."""
import subprocess

# Só o toolset mínimo (sem terminal: o prompt traz texto de e-mail): 2,8 mil tokens em vez de 19 mil.
# 2026-10-29: `--reasoning none` saiu. O provedor agora é o Antigravity pelo 9router, cujos modelos
# Gemini não aceitam o campo (thinkingCanDisable=false): a chamada levava 400 e o Hermes repetia sem
# o campo. O nível de raciocínio passou a vir do nome do modelo no perfil — `ag/gemini-3.8-flash-low`,
# medido em 0 token de raciocínio contra 60 do padrão. Enxugamento mantido, mecanismo trocado.
ENXUTO = ["-t", "todo", "--ignore-rules"]


def perguntar(prompt):
    r = subprocess.run(["hermes", "-z", prompt, *ENXUTO], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"hermes -z saiu com {r.returncode}")
    return r.stdout

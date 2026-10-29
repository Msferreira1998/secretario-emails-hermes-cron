"""Mensagens do Telegram: resumo diário, ensaio e plano de troca de cadastro das segundas."""

MAX_PENDENTES = 20


def linha_conta(nome, c, ensaio):
    if c.get("erro"):
        return f"{nome}: {c['erro']}"
    if not c["novos"]:
        return f"{nome}: sem novidades"
    pre = "seriam " if ensaio else ""
    return (f"{nome}: {pre}{c['rotulados']} rotulados, {c['arquivados']} arquivados, "
            f"{c['apagados']} apagados, {c['descadastrados']} descadastrados")


def montar(contas, pendentes, descadastrados, manual, avisos, ensaio, plano=None, sem_papel=(), ex=None):
    out = []
    if ensaio:
        out.append("🧪 Ensaio do secretário de e-mails — nada foi alterado. A partir da próxima faxina, é para valer.")
        out.append("Para vetar um descadastro: \"não descadastra <remetente>\". Para proteger: \"protege <remetente>\".")
    else:
        out.append("📬 Secretário de e-mails")
    if all(not c.get("erro") and not c["novos"] for c in contas.values()):
        out.append("Sem novidades desde a última faxina.")
    out.append("")
    out += [linha_conta(n, c, ensaio) for n, c in contas.items()]
    out += [f"{n}: {c['antigos']} antigos {'iriam para' if ensaio else 'na'} lixeira" for n, c in contas.items() if c.get("antigos")]
    out += [f"{n}: {c['fora_da_caixa']} {'sairiam' if ensaio else 'saíram'} da caixa de entrada (ficam no marcador)"
            for n, c in contas.items() if c.get("fora_da_caixa")]
    if pendentes:
        out += ["", "Precisa de você:"]
        for p in pendentes[:MAX_PENDENTES]:
            out.append(f"{p['codigo']} — {p['nome'] or p['de']} ({p['conta']}): {p['assunto']}")
        if len(pendentes) > MAX_PENDENTES:
            out.append(f"… e mais {len(pendentes) - MAX_PENDENTES} na caixa de entrada.")
        out.append("Para responder: \"responde <código> que …\".")
    out += _extras(ex or {})
    if descadastrados:
        out += ["", "Seriam descadastrados:" if ensaio else "Descadastrados:"]
        out += [f"- {d}" for d in sorted(descadastrados)]
    if manual:
        out += ["", "Descadastre você mesmo (o remetente não oferece descadastro automático):"]
        out += [f"- {d}" for d in sorted(manual)]
    if plano:
        out += ["", "Plano de troca de cadastro:"]
        out += [f"- Troque o cadastro da {nome} para a conta {certa} ({n} e-mails/semana)" for nome, certa, n in plano]
    for conta in sem_papel:
        out.append(f"\n➡️ defina o papel da conta {conta} para eu separar os e-mails: mande \"papel {conta} <trabalho|pessoal|compras…>\".")
    for a in avisos:
        out.append(f"⚠️ {a}")
    return "\n".join(out)


def _extras(ex):
    out = []
    if ex.get("golpes"):
        out += ["", "⚠️ Possível golpe (não clique em links; ficou na caixa de entrada):"]
        out += [f"- {m['nome']} <{m['de']}> ({m['conta']}): {m['assunto']}" for m in ex["golpes"][:MAX_PENDENTES]]
    for quando in ("hoje", "amanhã"):
        itens = [v for v in ex.get("vencem", ()) if v["quando"] == quando]
        if itens:
            out += ["", f"💸 Vence {quando}:"]
            out += [f"- {v['nome'] or v['de']} ({v['conta']}): {v['assunto']}" for v in itens]
    if ex.get("pedidos"):
        out += ["", f"📦 A caminho ({len(ex['pedidos'])}):"]
        out += [f"- {loja} ({conta}): {assunto}" for loja, assunto, conta in ex["pedidos"][:5]]
    if ex.get("recorrentes"):
        out += ["", "🔁 Cobranças recorrentes (confira se ainda usa):"]
        out += [f"- {dom} ({n} meses)" for dom, n in sorted(ex["recorrentes"].items(), key=lambda x: -x[1])]
    if ex.get("aprendidos"):
        out += ["", "🧠 Aprendi com você (para desfazer: \"regra <remetente> <tipo>\"):"]
        out += [f"- {de} → {tipo}" for de, tipo in ex["aprendidos"]]
    return out

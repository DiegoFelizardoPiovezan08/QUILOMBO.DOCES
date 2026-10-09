# app.py
# Aplicacao web com Flask — CRUD completo de doces pelo navegador
# Projeto: Quilombo Doces

from flask import Flask, request, render_template, redirect, url_for,session
from cadastro_sqlite import conectar_banco, validar_preco
from urllib.parse import quote
from flask import (Flask, request, render_template, redirect,url_for, session, flash)


app = Flask(__name__)


app.secret_key = "Neymar"
WHATSAPP = "5511998325340"  # seu número com DDI + DDD
# --------------------------------------------------------------- LEITURA (GET)

@app.route("/")
def listar():
    """Pagina inicial: todos os doces cadastrados."""
    conn = conectar_banco()
    doces = conn.execute(
        'SELECT * FROM doces ORDER BY nome').fetchall()
    conn.close()

    #a mensagem de sucesso chega pela URL, apos o redirect
    return render_template("lista.html", doces=doces,
                           msg=request.args.get("msg", ""))


@app.route("/doce/<int:id_doce>")
def detalhe(id_doce):
    """Pagina de um doce especifico."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()
    conn.close()

    if doce is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    return render_template("detalhe.html", doce=doce)


@app.route("/buscar")
def buscar():
    """Busca por nome. O termo vem na URL: /buscar?termo=brigadeiro"""
    termo = request.args.get("termo", "").strip().lower()

    encontrados = []
    if termo:
        conn = conectar_banco()
        encontrados = conn.execute(
            'SELECT * FROM doces WHERE LOWER(nome) LIKE ? ORDER BY nome',
            (f'%{termo}%',)
        ).fetchall()
        conn.close()

    return render_template("busca.html", termo=termo, doces=encontrados)


@app.route("/sobre")
def sobre():
    """Pagina estatica de exemplo."""
    return render_template("sobre.html")


# --------------------------------------------------------------- VALIDACAO

def validar_formulario(dados, conn, id_atual=None):
    """Valida os dados vindos do formulario.

    Devolve um dicionario de erros: {campo: mensagem}.
    Dicionario vazio significa que esta tudo certo.
    """
    erros = {}

    if len(dados["nome"]) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    else:
        # regra que depende do banco: o nome do doce nao pode se repetir.
        # Ao EDITAR, o proprio registro nao conta como duplicata.
        if id_atual is None:
            existente = conn.execute(
                'SELECT id FROM doces WHERE LOWER(nome) = ?',
                (dados["nome"].lower(),)).fetchone()
        else:
            existente = conn.execute(
                'SELECT id FROM doces WHERE LOWER(nome) = ? AND id <> ?',
                (dados["nome"].lower(), id_atual)).fetchone()
        if existente:
            erros["nome"] = "Ja existe um doce com esse nome."

    if not validar_preco(dados["preco"]):
        erros["preco"] = "Informe um preco valido, maior que zero (exemplo: 18,50)."

    return erros


def ler_formulario():
    """Le os campos enviados e devolve um dicionario ja limpo."""
    return {
        "nome": request.form.get("nome", "").strip(),
        "preco": request.form.get("preco", "").strip(),
    }


# --------------------------------------------------------------- CADASTRAR

@app.route("/novo", methods=["GET", "POST"])
def novo():
    """GET exibe o formulario; POST grava o doce."""
    if request.method == "GET":
        return render_template("form.html", titulo="Cadastrar doce",
                               dados={}, erros={}, acao=url_for("novo"))

    dados = ler_formulario()

    conn = conectar_banco()
    erros = validar_formulario(dados, conn)

    if erros:
        conn.close()
        # devolve o formulario COM o que foi digitado e as mensagens
        return render_template("form.html", titulo="Cadastrar doce",
                               dados=dados, erros=erros,
                               acao=url_for("novo")), 400

    conn.execute(
        'INSERT INTO doces (nome, preco) VALUES (?, ?)',
        (dados["nome"].title(),
         round(float(dados["preco"].replace(",", ".")), 2)))
    conn.commit()
    conn.close()

    # POST-Redirect-GET: nunca devolver a pagina direto depois de gravar
    return redirect(url_for("listar", msg="Doce cadastrado com sucesso!"))


# --------------------------------------------------------------- EDITAR

@app.route("/doce/<int:id_doce>/editar", methods=["GET", "POST"])
def editar(id_doce):
    """GET exibe o formulario preenchido; POST grava a alteracao."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()

    if doce is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    if request.method == "GET":
        conn.close()
        # dict(doce) converte a linha do banco em dicionario
        dados = dict(doce)
        dados["preco"] = f"{doce['preco']:.2f}".replace(".", ",")
        return render_template("form.html", titulo=f"Editar {doce['nome']}",
                               dados=dados, erros={},
                               acao=url_for("editar", id_doce=id_doce))

    dados = ler_formulario()
    erros = validar_formulario(dados, conn, id_atual=id_doce)

    if erros:
        conn.close()
        return render_template("form.html", titulo=f"Editar {doce['nome']}",
                               dados=dados, erros=erros,
                               acao=url_for("editar", id_doce=id_doce)), 400

    conn.execute(
        'UPDATE doces SET nome = ?, preco = ? WHERE id = ?',
        (dados["nome"].title(),
         round(float(dados["preco"].replace(",", ".")), 2),
         id_doce))
    conn.commit()
    conn.close()

    return redirect(url_for("listar", msg="Dados atualizados com sucesso!"))


# --------------------------------------------------------------- EXCLUIR

@app.route("/doce/<int:id_doce>/excluir", methods=["POST"])
def excluir(id_doce):
    """Exclui o doce. Aceita SOMENTE POST — um link nao pode apagar dados."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()

    if doce is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    conn.execute('DELETE FROM doces WHERE id = ?', (id_doce,))
    conn.commit()
    conn.close()

    return redirect(url_for("listar",
                            msg=f"Registro de {doce['nome']} excluido."))


@app.errorhandler(404)
def pagina_nao_encontrada(erro):
    return render_template("erro.html",
                           mensagem="Confira o endereco digitado."), 404



# --------------------------------------------------------------- CARRINHO

@app.route("/carrinho/adicionar/<int:id>", methods=["POST"])
def adicionar_carrinho(id):
    carrinho = session.get("carrinho", {})
    chave = str(id)
    carrinho[chave] = carrinho.get(chave, 0) + 1
    session["carrinho"] = carrinho
    return redirect(request.referrer or url_for("carrinho"))


@app.route("/carrinho")
def carrinho():
    itens = []
    total = 0

    conn = conectar_banco()
    for chave, qtd in session.get("carrinho", {}).items():
        doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                            (int(chave),)).fetchone()
        if doce is None:      # doce foi excluído depois de entrar no carrinho
            continue
        subtotal = doce["preco"] * qtd
        total += subtotal
        itens.append({"id": doce["id"], "nome": doce["nome"],
                      "preco": doce["preco"], "qtd": qtd, "subtotal": subtotal})
    conn.close()

    linhas = ["Olá! Gostaria de fazer este pedido:"]
    for i in itens:
        linhas.append(f"- {i['qtd']}x {i['nome']} (R$ {i['subtotal']:.2f})")
    linhas.append(f"Total: R$ {total:.2f}")
    link_whatsapp = f"https://wa.me/{WHATSAPP}?text={quote(chr(10).join(linhas))}"

    return render_template("carrinho.html", itens=itens, total=total,
                           link_whatsapp=link_whatsapp)


@app.route("/carrinho/remover/<int:id>", methods=["POST"])
def remover_carrinho(id):
    carrinho = session.get("carrinho", {})
    carrinho.pop(str(id), None)
    session["carrinho"] = carrinho
    return redirect(url_for("carrinho"))


@app.route("/carrinho/limpar", methods=["POST"])
def limpar_carrinho():
    session.pop("carrinho", None)
    return redirect(url_for("carrinho"))


@app.template_filter("brl")
def formato_brl(valor):
    """Mostra 18.5 como 18,50 (usado nos templates: {{ preco|brl }})."""
    return f"{float(valor):.2f}".replace(".", ",")


@app.context_processor
def dados_globais():
    """Variaveis disponiveis em TODOS os templates."""
    return {
        "qtd_carrinho": sum(session.get("carrinho", {}).values()),
        "whatsapp": WHATSAPP,
    }


def montar_carrinho():
    """Le o carrinho da sessao e devolve (itens, total, link_whatsapp)."""
    itens = []
    total = 0

    conn = conectar_banco()
    for chave, qtd in session.get("carrinho", {}).items():
        doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                            (int(chave),)).fetchone()
        if doce is None:          # doce excluido depois de entrar no carrinho
            continue
        subtotal = doce["preco"] * qtd
        total += subtotal
        itens.append({"id": doce["id"], "nome": doce["nome"],
                      "preco": doce["preco"], "qtd": qtd,
                      "subtotal": subtotal})
    conn.close()

    linhas = ["Olá! Gostaria de fazer este pedido:"]
    for i in itens:
        linhas.append(f"- {i['qtd']}x {i['nome']} (R$ {i['subtotal']:.2f})")
    linhas.append(f"Total: R$ {total:.2f}")
    link = f"https://wa.me/{WHATSAPP}?text={quote(chr(10).join(linhas))}"

    return itens, total, link


# ----------------------------------------------------------- VITRINE

@app.route("/loja")
def loja():
    """Vitrine: todos os doces, ou o resultado de uma busca."""
    termo = request.args.get("termo", "").strip().lower()

    conn = conectar_banco()
    if termo:
        doces = conn.execute(
            'SELECT * FROM doces WHERE LOWER(nome) LIKE ? ORDER BY nome',
            (f'%{termo}%',)).fetchall()
    else:
        doces = conn.execute('SELECT * FROM doces ORDER BY nome').fetchall()
    conn.close()

    return render_template("loja.html", doces=doces, termo=termo)


@app.route("/loja/doce/<int:id_doce>")
def loja_produto(id_doce):
    """Pagina de um doce para o consumidor."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()
    conn.close()

    if doce is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    return render_template("loja_produto.html", doce=doce)


# ----------------------------------------------------------- CARRINHO

@app.route("/loja/carrinho")
def loja_carrinho():
    itens, total, link_whatsapp = montar_carrinho()
    return render_template("loja_carrinho.html", itens=itens, total=total,
                           link_whatsapp=link_whatsapp)


@app.route("/loja/carrinho/adicionar/<int:id_doce>", methods=["POST"])
def loja_adicionar(id_doce):
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()
    conn.close()

    if doce is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    # quantidade vem do campo da pagina do produto (na vitrine nao tem: vale 1)
    try:
        qtd = int(request.form.get("quantidade", "1"))
    except ValueError:
        qtd = 1
    qtd = max(1, min(qtd, 99))

    carrinho = session.get("carrinho", {})
    chave = str(id_doce)
    carrinho[chave] = carrinho.get(chave, 0) + qtd
    session["carrinho"] = carrinho

    flash(f"{doce['nome']} adicionado ao carrinho!")
    return redirect(request.referrer or url_for("loja"))


@app.route("/loja/carrinho/atualizar/<int:id_doce>", methods=["POST"])
def loja_atualizar(id_doce):
    """Botoes de + e - no carrinho."""
    carrinho = session.get("carrinho", {})
    chave = str(id_doce)

    if chave in carrinho:
        if request.form.get("acao") == "mais":
            carrinho[chave] = min(carrinho[chave] + 1, 99)
        else:
            carrinho[chave] -= 1
        if carrinho[chave] <= 0:      # chegou a zero: tira do carrinho
            carrinho.pop(chave)

    session["carrinho"] = carrinho
    return redirect(url_for("loja_carrinho"))


@app.route("/loja/carrinho/remover/<int:id_doce>", methods=["POST"])
def loja_remover(id_doce):
    carrinho = session.get("carrinho", {})
    carrinho.pop(str(id_doce), None)
    session["carrinho"] = carrinho
    return redirect(url_for("loja_carrinho"))


@app.route("/loja/carrinho/limpar", methods=["POST"])
def loja_limpar():
    session.pop("carrinho", None)
    return redirect(url_for("loja_carrinho"))

if __name__ == "__main__":
    app.run(debug=True)



# app.py
# Aplicacao web com Flask — CRUD completo de doces pelo navegador
# Projeto: Quilombo Doces

import os
import uuid
from datetime import datetime

import qrcode
import qrcode.image.svg

from flask import (Flask, request, render_template, redirect, url_for,
                   session, flash)
from cadastro_sqlite import conectar_banco, validar_preco
from contas import contas, cliente_atual, endereco_completo
from urllib.parse import quote


app = Flask(__name__)
app.register_blueprint(contas)      # paginas de conta do cliente (contas.py)


app.secret_key = "Neymar"
WHATSAPP = "5511998325340"  # seu número com DDI + DDD

# --------------------------------------------------------------- PIX
# dados de quem recebe o Pix (aparecem no app do banco de quem paga)
PIX_CHAVE = "39656059840"     # chave Pix: CPF 396.560.598-40, so os numeros
PIX_NOME = "QUILOMBO DOCES"   # ate 25 letras, sem acento
PIX_CIDADE = "SAO PAULO"      # ate 15 letras, sem acento


def campo_pix(codigo, valor):
    """Monta um campo do Pix: codigo (2 digitos) + tamanho (2 digitos) + valor."""
    return f"{codigo}{len(valor):02d}{valor}"


def crc16_pix(texto):
    """Digito verificador do Pix (CRC16-CCITT), exigido pelo Banco Central."""
    crc = 0xFFFF
    for byte in texto.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def gerar_pix(valor, identificador="***"):
    """Gera o "Pix copia e cola" (padrao do Banco Central) com o valor ja preenchido.

    identificador: codigo do pedido (ate 25 letras/numeros). Aparece no
    comprovante e, em muitos bancos, no extrato de quem recebe.
    """
    conta = campo_pix("00", "br.gov.bcb.pix") + campo_pix("01", PIX_CHAVE)
    codigo = (campo_pix("00", "01")                 # versao do padrao
              + campo_pix("26", conta)              # chave Pix
              + campo_pix("52", "0000")
              + campo_pix("53", "986")              # moeda: real
              + campo_pix("54", f"{valor:.2f}")     # valor do pedido
              + campo_pix("58", "BR")
              + campo_pix("59", PIX_NOME)
              + campo_pix("60", PIX_CIDADE)
              + campo_pix("62", campo_pix("05", identificador))
              + "6304")                             # o CRC vem logo depois
    return codigo + crc16_pix(codigo)


def qrcode_svg(texto):
    """Desenha o QR Code do texto e devolve como SVG (vai direto no HTML)."""
    imagem = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage,
                         box_size=10, border=2)
    return imagem.to_string(encoding="unicode")

# --------------------------------------------------------------- IMAGENS

# as fotos enviadas ficam em static/uploads (a pasta e criada sozinha)
PASTA_UPLOADS = os.path.join(app.root_path, "static", "uploads")
EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024   # limite: 5 MB por envio


def ler_imagem(campo="imagem"):
    """Le a foto enviada no formulario.

    Devolve (arquivo, erro). arquivo e None quando nada foi enviado.
    """
    arquivo = request.files.get(campo)
    if arquivo is None or arquivo.filename == "":
        return None, None

    extensao = arquivo.filename.rsplit(".", 1)[-1].lower()
    if "." not in arquivo.filename or extensao not in EXTENSOES_IMAGEM:
        return None, "Envie uma imagem JPG, PNG, GIF ou WEBP."

    return arquivo, None


def salvar_imagem(arquivo):
    """Grava a foto em static/uploads com um nome unico e devolve esse nome."""
    os.makedirs(PASTA_UPLOADS, exist_ok=True)
    extensao = arquivo.filename.rsplit(".", 1)[-1].lower()
    nome = f"{uuid.uuid4().hex}.{extensao}"
    arquivo.save(os.path.join(PASTA_UPLOADS, nome))
    return nome


def apagar_imagem(nome):
    """Apaga a foto antiga (quando o registro e excluido ou a foto trocada)."""
    if nome:
        caminho = os.path.join(PASTA_UPLOADS, nome)
        if os.path.exists(caminho):
            os.remove(caminho)


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
        "descricao": request.form.get("descricao", "").strip(),
        # caixinha marcada = 1 (vai para os Destaques), desmarcada = 0
        "destaque": 1 if request.form.get("destaque") else 0,
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
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        # devolve o formulario COM o que foi digitado e as mensagens
        return render_template("form.html", titulo="Cadastrar doce",
                               dados=dados, erros=erros,
                               acao=url_for("novo")), 400

    imagem = salvar_imagem(arquivo) if arquivo else None

    conn.execute(
                        'INSERT INTO doces (nome, preco, descricao, destaque, imagem) VALUES (?, ?, ?, ?, ?)',
        (dados["nome"].title(),
         round(float(dados["preco"].replace(",", ".")), 2),
         dados["descricao"],
         dados["destaque"],
         imagem))
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
    dados["imagem"] = doce["imagem"]     # para o formulario mostrar a foto atual
    erros = validar_formulario(dados, conn, id_atual=id_doce)
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        return render_template("form.html", titulo=f"Editar {doce['nome']}",
                               dados=dados, erros=erros,
                               acao=url_for("editar", id_doce=id_doce)), 400

    # foto: troca se veio uma nova, apaga se marcou "remover", senao mantem
    imagem = doce["imagem"]
    if arquivo:
        apagar_imagem(imagem)
        imagem = salvar_imagem(arquivo)
    elif request.form.get("remover_imagem"):
        apagar_imagem(imagem)
        imagem = None

    conn.execute(
                         'UPDATE doces SET nome = ?, preco = ?, descricao = ?, destaque = ?, imagem = ? WHERE id = ?',
        (dados["nome"].title(),
         round(float(dados["preco"].replace(",", ".")), 2),
         dados["descricao"],
         dados["destaque"],
         imagem,
         id_doce))
    conn.commit()
    conn.close()

    return redirect(url_for("listar", msg="Dados atualizados com sucesso!"))


# --------------------------------------------------------------- EXCLUIR
@app.route("/doce/<int:id_doce>/destaque", methods=["POST"])
def alternar_destaque(id_doce):
    """Botao da estrela na lista: coloca ou tira o doce dos Destaques."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()

    if doce is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    novo = 0 if doce["destaque"] else 1
    conn.execute('UPDATE doces SET destaque = ? WHERE id = ?', (novo, id_doce))
    conn.commit()
    conn.close()

    if novo:
        msg = f"{doce['nome']} agora aparece nos Destaques da loja."
    else:
        msg = f"{doce['nome']} saiu dos Destaques (continua em Produtos)."
    return redirect(url_for("listar", msg=msg))


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
    apagar_imagem(doce["imagem"])

    return redirect(url_for("listar",
                            msg=f"Registro de {doce['nome']} excluido."))


@app.errorhandler(404)
def pagina_nao_encontrada(erro):
    return render_template("erro.html",
                           mensagem="Confira o endereco digitado."), 404


@app.errorhandler(413)
def arquivo_grande(erro):
    return render_template("erro.html", titulo="Arquivo muito grande",
                           mensagem="A imagem deve ter no maximo 5 MB."), 413



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



def dados_globais():
    """Variaveis disponiveis em TODOS os templates."""
    return {
        "qtd_carrinho": sum(session.get("carrinho", {}).values()),
        "whatsapp": WHATSAPP,
    }

@app.context_processor
def dados_globais():
    """Variaveis disponiveis em TODOS os templates."""
    return {
        "qtd_carrinho": sum(session.get("carrinho", {}).values()),
        "whatsapp": WHATSAPP,
        "pedidos_pendentes": contar_pedidos_pendentes(),
        "cliente": cliente_atual(),      # cliente logado na loja (ou None)
    }


def contar_pedidos_pendentes():
    """Quantos clientes avisaram que pagaram e esperam a conferencia (aba Pedidos)."""
    conn = conectar_banco()
    qtd = conn.execute(
        "SELECT COUNT(*) FROM pedidos WHERE status = 'informado'").fetchone()[0]
    conn.close()
    return qtd


@app.template_filter("link_whatsapp")
def link_whatsapp_cliente(telefone):
    """Link para chamar o cliente no WhatsApp (aceita "11 99999-9999", "(11)..." etc.)."""
    digitos = "".join(c for c in telefone if c.isdigit())
    if len(digitos) <= 11:              # sem o 55 do Brasil na frente
        digitos = "55" + digitos
    return f"https://wa.me/{digitos}"


@app.template_filter("numero_pedido")
def numero_pedido(id_pedido):
    """Mostra o id 7 como #0007."""
    return f"#{id_pedido:04d}"


def link_whatsapp_pedido(pedido):
    """Link do WhatsApp da loja com o pedido JA CONFIRMADO escrito."""
    texto = (f"Olá! Meu pedido {numero_pedido(pedido['id'])} teve o pagamento "
             f"confirmado:\n{pedido['itens']}\nTotal: R$ {formato_brl(pedido['total'])}")
    return f"https://wa.me/{WHATSAPP}?text={quote(texto)}"

@app.template_filter("aviso_pagamento")
def link_aviso_pagamento(pedido):
    """Link que abre o WhatsApp da loja ja com a mensagem para o CLIENTE
    dizendo que o pagamento foi confirmado (o administrador so aperta enviar)."""
    nome = pedido["nome"].split()[0] if pedido["nome"] else ""
    endereco_pedido = url_for("loja_pedido", token=pedido["token"], _external=True)
    texto = (f"Olá, {nome}! Aqui é da Quilombo Doces.\n\n"
             f"Recebemos o seu Pix e o pagamento do pedido "
             f"{numero_pedido(pedido['id'])} foi CONFIRMADO! ✅\n\n"
             f"{pedido['itens']}\n"
             f"Total: R$ {formato_brl(pedido['total'])}\n\n"
             f"Já estamos preparando tudo com carinho. "
             f"Acompanhe o seu pedido aqui: {endereco_pedido}")
    return f"{link_whatsapp_cliente(pedido['telefone'])}?text={quote(texto)}"

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
                      "subtotal": subtotal, "imagem": doce["imagem"]})
    conn.close()

    linhas = ["Olá! Fiz este pedido e já paguei pelo Pix:"]
    for i in itens:
        linhas.append(f"- {i['qtd']}x {i['nome']} (R$ {i['subtotal']:.2f})")
    linhas.append(f"Total: R$ {total:.2f}")
    linhas.append("Segue o comprovante.")
    link = f"https://wa.me/{WHATSAPP}?text={quote(chr(10).join(linhas))}"

    return itens, total, link


# ----------------------------------------------------------- VITRINE

@app.route("/loja")
def loja():
    """Pagina inicial da loja: carrossel e destaques."""
    conn = conectar_banco()
    # cada foto vira {"arquivo": caminho dentro de static, "legenda": texto}
    slides = [{"arquivo": "uploads/" + s["imagem"], "legenda": s["legenda"]}
              for s in conn.execute('SELECT * FROM carrossel ORDER BY id')]
        # so os doces marcados como destaque (todos continuam na aba Produtos)
    doces = conn.execute(
        'SELECT * FROM doces WHERE destaque = 1 ORDER BY nome').fetchall()
    conn.close()

    # nenhuma foto cadastrada na aba Carrossel: usa as fotos de static/img
    # (carrossel-1.jpg ate carrossel-4.jpg), se existirem
    if not slides:
        for n in range(1, 5):
            arquivo = f"img/carrossel-{n}.jpg"
            if os.path.exists(os.path.join(app.static_folder, arquivo)):
                slides.append({"arquivo": arquivo, "legenda": ""})

    return render_template("loja.html", slides=slides, doces=doces)


@app.route("/loja/produtos")
def loja_produtos():
    """Botao "Produtos": todos os doces, ou o resultado de uma busca."""
    termo = request.args.get("termo", "").strip().lower()

    conn = conectar_banco()
    if termo:
        doces = conn.execute(
            'SELECT * FROM doces WHERE LOWER(nome) LIKE ? ORDER BY nome',
            (f'%{termo}%',)).fetchall()
    else:
        doces = conn.execute('SELECT * FROM doces ORDER BY nome').fetchall()
    conn.close()

    return render_template("loja_produtos.html", doces=doces, termo=termo)


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


@app.route("/loja/eventos")
def loja_eventos():
    """Botao "Eventos": todos os eventos para o consumidor."""
    conn = conectar_banco()
    eventos = conn.execute('SELECT * FROM eventos ORDER BY nome').fetchall()
    conn.close()

    return render_template("loja_eventos.html", eventos=eventos)


@app.route("/loja/evento/<int:id_evento>")
def loja_evento(id_evento):
    """Pagina de um evento para o consumidor."""
    conn = conectar_banco()
    evento = conn.execute('SELECT * FROM eventos WHERE id = ?',
                          (id_evento,)).fetchone()
    conn.close()

    if evento is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe evento com id {id_evento}."), 404

    texto = f"Olá! Tenho interesse no evento: {evento['nome']}"
    link_whatsapp = f"https://wa.me/{WHATSAPP}?text={quote(texto)}"

    return render_template("loja_evento.html", evento=evento,
                           link_whatsapp=link_whatsapp)


@app.route("/loja/sobre")
def loja_sobre():
    """Botao "Sobre": a historia da loja para o consumidor."""
    conn = conectar_banco()
    sobre = conn.execute('SELECT * FROM sobre ORDER BY id LIMIT 1').fetchone()
    conn.close()

    return render_template("loja_sobre.html", sobre=sobre)


# ----------------------------------------------------------- CARRINHO

@app.route("/loja/carrinho")
def loja_carrinho():
    itens, total, link_whatsapp = montar_carrinho()

    # cliente logado: mostra tambem os pedidos que ainda estao no pagamento,
    # para ele voltar de onde parou mesmo depois de sair ou atualizar a pagina
    pedidos_abertos = []
    cliente = cliente_atual()
    if cliente:
        conn = conectar_banco()
        pedidos_abertos = conn.execute(
            "SELECT * FROM pedidos WHERE cliente_id = ? "
            "AND status IN ('aguardando', 'informado') ORDER BY id DESC",
            (cliente["id"],)).fetchall()
        conn.close()

    return render_template("loja_carrinho.html", itens=itens, total=total,
                           link_whatsapp=link_whatsapp,
                           pedidos_abertos=pedidos_abertos)


# ----------------------------------------------------------- PEDIDOS (PIX)
# 1. /loja/pagamento: o cliente entra na conta (ou cria) e confirma os dados
# 2. /loja/pedido/<token>: QR Code do Pix com o numero do pedido
# 3. o cliente clica em "Ja fiz o Pix" -> status "informado"
# 4. o administrador confere no banco e clica em "Confirmar pagamento"
# 5. so entao a pagina do cliente mostra "Pagamento confirmado"
# Os pedidos ficam na conta do cliente ("Minha conta" e Carrinho).

@app.route("/loja/pagamento", methods=["GET", "POST"])
def loja_pagamento():
    """GET mostra os dados de entrega; POST cria o pedido e esvazia o carrinho."""
    itens, total, _ = montar_carrinho()

    if not itens:                       # carrinho vazio: nada para pagar
        return redirect(url_for("loja_carrinho"))

    cliente = cliente_atual()
    if cliente is None:                 # precisa entrar; depois volta para ca
        flash("Entre na sua conta (ou crie uma) para finalizar o pedido.")
        return redirect(url_for("contas.entrar", proximo=url_for("loja_pagamento")))

    if request.method == "GET":
        return render_template("loja_pagamento.html", itens=itens, total=total,
                               endereco=endereco_completo(cliente))

    # os itens ficam guardados como texto: o pedido nao muda se o preco mudar depois
    texto_itens = "\n".join(f"{i['qtd']}x {i['nome']} (R$ {formato_brl(i['subtotal'])})"
                             for i in itens)
    token = uuid.uuid4().hex[:12]       # endereco secreto da pagina do pedido

    conn = conectar_banco()
    conn.execute(
        'INSERT INTO pedidos (token, nome, telefone, itens, total, criado_em, '
        'cliente_id, cpf, endereco) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (token, cliente["nome"], cliente["telefone"], texto_itens, round(total, 2),
         datetime.now().strftime("%d/%m/%Y %H:%M"),
         cliente["id"], cliente["cpf"], endereco_completo(cliente)))
    conn.commit()
    conn.close()

    session.pop("carrinho", None)       # o carrinho virou pedido
    return redirect(url_for("loja_pedido", token=token))


@app.route("/loja/pedido/<token>")
def loja_pedido(token):
    """Pagina do pedido: Pix enquanto nao paga; depois mostra a confirmacao."""
    conn = conectar_banco()
    pedido = conn.execute('SELECT * FROM pedidos WHERE token = ?',
                          (token,)).fetchone()
    conn.close()

    if pedido is None:
        return render_template("erro.html",
                               mensagem="Pedido nao encontrado."), 404

    pix = qr = None
    if pedido["status"] in ("aguardando", "informado"):
        pix = gerar_pix(pedido["total"], f"QD{pedido['id']:05d}")
        qr = qrcode_svg(pix)

    return render_template("loja_pedido.html", pedido=pedido, pix=pix, qrcode=qr,
                           link_whatsapp=link_whatsapp_pedido(pedido))


@app.route("/loja/pedido/<token>/paguei", methods=["POST"])
def loja_pedido_paguei(token):
    """Botao "Ja fiz o Pix": avisa o administrador para conferir."""
    conn = conectar_banco()
    conn.execute("UPDATE pedidos SET status = 'informado' "
                 "WHERE token = ? AND status = 'aguardando'", (token,))
    conn.commit()
    conn.close()
    return redirect(url_for("loja_pedido", token=token))

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

# ----------------------------------------------------------- EVENTOS

@app.route("/eventos")
def eventos():  
    """Pagina inicial: todos os eventos cadastrados."""
    conn = conectar_banco()
    eventos = conn.execute(
        'SELECT * FROM eventos ORDER BY nome').fetchall()
    conn.close()

    #a mensagem de sucesso chega pela URL, apos o redirect
    return render_template("eventos.html", eventos=eventos,
                           msg=request.args.get("msg", "")) 

@app.route("/novo_evento", methods=["GET", "POST"])
def novo_evento():
    """GET exibe o formulario; POST grava o evento."""
    if request.method == "GET":
        return render_template("form_evento.html", titulo="Cadastrar evento",
                               dados={}, erros={}, acao=url_for("novo_evento"))

    dados = {
        "nome": request.form.get("nome", "").strip(),
        "descricao": request.form.get("descricao", "").strip(),
        # caixinha marcada = 1 (vai para os Destaques), desmarcada = 0
        "destaque": 1 if request.form.get("destaque") else 0,
    }

    conn = conectar_banco()
    erros = {}
    if len(dados["nome"]) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        return render_template("form_evento.html", titulo="Cadastrar evento",
                               dados=dados, erros=erros,
                               acao=url_for("novo_evento")), 400

    imagem = salvar_imagem(arquivo) if arquivo else None

    conn.execute(
        'INSERT INTO eventos (nome, descricao, imagem) VALUES (?, ?, ?)',
        (dados["nome"].title(), dados["descricao"], imagem))
    conn.commit()
    conn.close()

    return redirect(url_for("eventos", msg="Evento cadastrado com sucesso!"))

@app.route("/evento/<int:id_evento>/editar", methods=["GET", "POST"])
def editar_evento(id_evento):       
    """GET exibe o formulario preenchido; POST grava a alteracao."""
    conn = conectar_banco()
    evento = conn.execute('SELECT * FROM eventos WHERE id = ?',
                        (id_evento,)).fetchone()

    if evento is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe evento com id {id_evento}."), 404

    if request.method == "GET":
        conn.close()
        dados = dict(evento)
        return render_template("form_evento.html", titulo=f"Editar {evento['nome']}",
                               dados=dados, erros={},
                               acao=url_for("editar_evento", id_evento=id_evento))

    dados = {
        "nome": request.form.get("nome", "").strip(),
        "descricao": request.form.get("descricao", "").strip(),
        "imagem": evento["imagem"],
    }
    erros = {}
    if len(dados["nome"]) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        return render_template("form_evento.html", titulo=f"Editar {evento['nome']}",
                               dados=dados, erros=erros,
                               acao=url_for("editar_evento", id_evento=id_evento)), 400

    imagem = evento["imagem"]
    if arquivo:
        apagar_imagem(imagem)
        imagem = salvar_imagem(arquivo)
    elif request.form.get("remover_imagem"):
        apagar_imagem(imagem)
        imagem = None

    conn.execute(
        'UPDATE eventos SET nome = ?, descricao = ?, imagem = ? WHERE id = ?',
        (dados["nome"].title(), dados["descricao"], imagem, id_evento))
    conn.commit()
    conn.close()

    return redirect(url_for("eventos", msg="Dados do evento atualizados com sucesso!"))

@app.route("/evento/<int:id_evento>/excluir", methods=["POST"])
def excluir_evento(id_evento):
    """Exclui o evento. Aceita SOMENTE POST — um link nao pode apagar dados."""
    conn = conectar_banco()
    evento = conn.execute('SELECT * FROM eventos WHERE id = ?',
                        (id_evento,)).fetchone()

    if evento is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe evento com id {id_evento}."), 404

    conn.execute('DELETE FROM eventos WHERE id = ?', (id_evento,))
    conn.commit()
    conn.close()
    apagar_imagem(evento["imagem"])

    return redirect(url_for("eventos",
                            msg=f"Registro de {evento['nome']} excluido."))

# ----------------------------------------------------------- SOBRE

@app.route("/sobre", methods=["GET", "POST"])
def sobre():
    """Pagina "Sobre" da loja: UMA foto e o texto embaixo.

    GET mostra o formulario ja preenchido; POST grava (cria na primeira vez,
    depois so atualiza o mesmo registro).
    """
    conn = conectar_banco()
    atual = conn.execute('SELECT * FROM sobre ORDER BY id LIMIT 1').fetchone()

    if request.method == "GET":
        conn.close()
        return render_template("sobre.html", dados=dict(atual) if atual else {},
                               erros={}, msg=request.args.get("msg", ""))

    dados = {
        "titulo": request.form.get("titulo", "").strip(),
        "texto": request.form.get("texto", "").strip(),
        "imagem": atual["imagem"] if atual else None,
    }
    arquivo, erro_imagem = ler_imagem()

    # foto: troca se veio uma nova, apaga se marcou "remover", senao mantem
    imagem = dados["imagem"]
    if request.form.get("remover_imagem") and arquivo is None:
        imagem = None

    erros = {}
    if erro_imagem:
        erros["imagem"] = erro_imagem
    elif not dados["texto"] and arquivo is None and imagem is None:
        erros["texto"] = "Escreva um texto ou envie uma foto."

    if erros:
        conn.close()
        return render_template("sobre.html", dados=dados, erros=erros, msg=""), 400

    if arquivo:
        apagar_imagem(dados["imagem"])
        imagem = salvar_imagem(arquivo)
    elif imagem is None:
        apagar_imagem(dados["imagem"])

    if atual:
        conn.execute('UPDATE sobre SET titulo = ?, texto = ?, imagem = ? WHERE id = ?',
                     (dados["titulo"], dados["texto"], imagem, atual["id"]))
        # se ficaram blocos da versao antiga (varios blocos), apaga os extras
        for extra in conn.execute('SELECT * FROM sobre WHERE id <> ?',
                                  (atual["id"],)).fetchall():
            apagar_imagem(extra["imagem"])
        conn.execute('DELETE FROM sobre WHERE id <> ?', (atual["id"],))
    else:
        conn.execute('INSERT INTO sobre (titulo, texto, imagem) VALUES (?, ?, ?)',
                     (dados["titulo"], dados["texto"], imagem))
    conn.commit()
    conn.close()

    return redirect(url_for("sobre", msg="Página Sobre salva com sucesso!"))

# ----------------------------------------------------------- PEDIDOS (ADMIN)

@app.route("/pedidos")
def pedidos():
    """Aba Pedidos: primeiro os que esperam conferencia, depois os mais novos."""
    conn = conectar_banco()
    lista = conn.execute(
        "SELECT * FROM pedidos ORDER BY "
        "CASE status WHEN 'informado' THEN 0 WHEN 'aguardando' THEN 1 ELSE 2 END, "
                "id DESC").fetchall()
    conn.close()

    return render_template("pedidos.html", pedidos=lista,
                           msg=request.args.get("msg", ""))
@app.route("/pedido/<int:id_pedido>/<acao>", methods=["POST"])
def mudar_pedido(id_pedido, acao):
    """Botoes "Confirmar pagamento" e "Cancelar" da aba Pedidos."""
    novo_status = {"confirmar": "pago", "cancelar": "cancelado"}.get(acao)
    if novo_status is None:
        return render_template("erro.html", mensagem="Acao invalida."), 404

    conn = conectar_banco()
    conn.execute('UPDATE pedidos SET status = ? WHERE id = ?',
                 (novo_status, id_pedido))
    conn.commit()
    conn.close()

    if novo_status == "pago":
        msg = f"Pagamento do pedido {numero_pedido(id_pedido)} confirmado."
    else:
        msg = f"Pedido {numero_pedido(id_pedido)} cancelado."
    return redirect(url_for("pedidos", msg=msg))




# ----------------------------------------------------------- CARROSSEL

@app.route("/carrossel", methods=["GET", "POST"])
def carrossel():
    """GET mostra as fotos do carrossel; POST adiciona uma foto nova."""
    conn = conectar_banco()
    erros = {}

    if request.method == "POST":
        arquivo, erro_imagem = ler_imagem()
        if arquivo is None and erro_imagem is None:
            erro_imagem = "Escolha uma imagem para enviar."

        if erro_imagem:
            erros["imagem"] = erro_imagem
        else:
            conn.execute(
                'INSERT INTO carrossel (imagem, legenda) VALUES (?, ?)',
                (salvar_imagem(arquivo), request.form.get("legenda", "").strip()))
            conn.commit()
            conn.close()
            return redirect(url_for("carrossel", msg="Foto adicionada ao carrossel!"))

    slides = conn.execute('SELECT * FROM carrossel ORDER BY id').fetchall()
    conn.close()

    return render_template("carrossel.html", slides=slides, erros=erros,
                           msg=request.args.get("msg", "")), (400 if erros else 200)


@app.route("/carrossel/<int:id_slide>/excluir", methods=["POST"])
def excluir_slide(id_slide):
    """Tira uma foto do carrossel e apaga o arquivo."""
    conn = conectar_banco()
    slide = conn.execute('SELECT * FROM carrossel WHERE id = ?',
                         (id_slide,)).fetchone()

    if slide is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe foto com id {id_slide}."), 404

    conn.execute('DELETE FROM carrossel WHERE id = ?', (id_slide,))
    conn.commit()
    conn.close()
    apagar_imagem(slide["imagem"])

    return redirect(url_for("carrossel", msg="Foto removida do carrossel."))


if __name__ == "__main__":
    app.run(debug=True)
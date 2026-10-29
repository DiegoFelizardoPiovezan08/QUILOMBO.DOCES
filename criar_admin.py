# criar_admin.py
# Cria um administrador (ou troca a senha de um que ja existe).
# Como usar: no terminal, dentro da pasta do projeto, rode
#     python criar_admin.py
# Projeto: Quilombo Doces

from getpass import getpass

from werkzeug.security import generate_password_hash

from cadastro_sqlite import conectar_banco


def main():
    print("=== Criar administrador da Quilombo Doces ===")
    usuario = input("Usuario: ").strip()
    if len(usuario) < 3:
        print("O usuario precisa ter pelo menos 3 letras.")
        return

    # getpass: a senha nao aparece na tela enquanto voce digita (e normal!)
    senha = getpass("Senha (nao aparece enquanto voce digita): ")
    if len(senha) < 8:
        print("A senha precisa ter pelo menos 8 caracteres.")
        return
    if getpass("Repita a senha: ") != senha:
        print("As senhas nao sao iguais. Nada foi salvo.")
        return

    # a senha e guardada embaralhada (hash): nem quem abrir o banco consegue le-la
    senha_hash = generate_password_hash(senha)

    conn = conectar_banco()
    if conn.execute('SELECT id FROM admins WHERE usuario = ?', (usuario,)).fetchone():
        conn.execute('UPDATE admins SET senha_hash = ? WHERE usuario = ?',
                     (senha_hash, usuario))
        print(f"Senha do administrador '{usuario}' trocada!")
    else:
        conn.execute('INSERT INTO admins (usuario, senha_hash) VALUES (?, ?)',
                     (usuario, senha_hash))
        print(f"Administrador '{usuario}' criado! Entre em http://127.0.0.1:5000/admin")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()

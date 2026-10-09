# main.py
# Ponto de entrada — sistema de cadastro de doces com SQLite
# Projeto: Quilombo Doces
 
from cadastro_sqlite import (
    mostrar_menu as menu_sqlite,
    cadastrar_doce, listar_doces, buscar_doce,
    editar_doce, excluir_doce
)
 
#mostra o titulo inicial ao entrar na pagina
def mostrar_titulo():
    """Exibe o titulo inicial do sistema."""
    print("\n" + "=" * 50)
    print("  QUILOMBO DOCES")
    print(" Sistema de Cadastro de Doces")
    print("=" * 50)
 

 #escolha de opcao quando for cadastrar o doce
def modo_sqlite():
    """Loop do modo SQLite — CRUD completo."""
    while True:
        menu_sqlite()
        opcao = input("Escolha uma opcao (1-6): ").strip()
        if opcao == "1":
            cadastrar_doce()
        elif opcao == "2":
            listar_doces()
        elif opcao == "3":
            buscar_doce()
        elif opcao == "4":
            editar_doce()
        elif opcao == "5":
            excluir_doce()
        elif opcao == "6":
            break
        else:
            print("Opcao invalida!")
 
#quando encerra o sistema
def main():
    """Funcao principal."""
    try:
        mostrar_titulo()
        modo_sqlite()
        print("\nAte logo!")
    except KeyboardInterrupt:
        print("\n\nSistema encerrado!")
 
 
if __name__ == "__main__":
    main()

---

# 🌱 ONG – Projeto extensionista da materia de Desenvolvimento web 3.

Este projeto é uma **landing page para ONG Coletivo Cultural Olhar da Perifa** feita em **Python + Flask + SQLite**, com formulário para interessados e área administrativa protegida por login.

---

## 📌 Funcionalidades já prontas

* ✅ **Landing Page** com seções:

  * Sobre a ONG
  * Projetos
  * Como Ajudar
  * Contato
  * Formulário de interesse (voluntariado/doações)
* ✅ **Banco de Dados SQLite** integrado (`database.db`)
* ✅ **Área Administrativa** protegida por login

  * Listagem dos interessados
  * Exclusão de registros
  * Exportação para **CSV**
* ✅ **Responsividade** usando **Bootstrap**
* ✅ **Login/Senha padrão**:

  * Usuário: `admin`
  * Senha: `senha123`

---

## ⚙️ Tecnologias usadas

* **Python 3**
* **Flask** (framework web)
* **SQLite** (banco de dados simples em arquivo `.db`)
* **Bootstrap 5** (responsividade e estilo)

---

## 🚀 Como rodar no Windows (CMD)

1. Entrar na pasta do projeto (VERIFIQUE A PASTA):

   ```cmd
   cd C:\Users\seu_usuario\Downloads\ong
   ```

2. Criar ambiente virtual (se ainda não existir):

   ```cmd
   py -3 -m venv venv
   ```

3. Ativar o ambiente:

   ```cmd
   venv\Scripts\activate.bat
   ```

4. Instalar dependências:

   ```cmd
   pip install -r requirements.txt
   ```

5. Rodar o projeto:

   ```cmd
   python app.py
   ```

6. Acessar no navegador:

   * Site: [http://127.0.0.1:5000](http://127.0.0.1:5000)
   * Admin: [http://127.0.0.1:5000/login](http://127.0.0.1:5000/login)

---

## 👨‍👩‍👧‍👦 O que falta (possíveis melhorias)

* Melhorar o design das páginas (HTML/CSS).
* Inserir fotos reais da ONG.
* Criar mais páginas/projetos se necessário.
* Alterar login/senha padrão para maior segurança.

---



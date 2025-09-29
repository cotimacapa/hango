# Hango

Sistema de pedidos e retirada de refeições com códigos de barras para escolas.

> Projeto originalmente desenvolvido pela **Coordenação de Tecnologia da Informação (COTI)** do **IFAP – Campus Macapá**.  
> Foco: velocidade, clareza e operação simples no dia a dia da cantina.

---

## ✨ Destaques

- **1 pedido por dia** por estudante, com **1 item por categoria** (ex.: “Almoço”, “Bebidas”).
- **Códigos de retirada** com **código de barras** (impressos e lidos no balcão).
- **Histórico do estudante** com *Mostrar código* (enquanto o pedido está pendente).
- **Página de supervisão (“Pedidos”)** com status, entrega, criado (data e hora) e **Exportar CSV**.
- **Planilha de códigos** pronta para impressão por dia.
- **Admin de Turmas** com:
  - botão **Ver lista de alunos** (roster com busca, paginação e impressão),
  - **vínculos de ano** (turma anterior/próximo ano),
  - **regra “1 turma por ano”** ao escolher membros (evita duplicidade).
- **Paginação** real nas telas longas do Admin (Usuários, Pedidos, Itens do pedido).
- **Tema escuro** com contrastes ajustados (rótulos legíveis, fundo branco do código de barras).

---

## 🧱 Stack

- **Django** (Python)
- HTML + Bulma (ou estilos equivalentes)
- Geração de código de barras (biblioteca Python)
- CSV export (nativo Django)
- Templates responsivos (mobile-first)

---

## 🚀 Começando

### Requisitos

- Python 3.11+
- Virtualenv (recomendado)
- Banco (SQLite por padrão; pode usar Postgres/MySQL)

### Instalação rápida

```bash
# 1) Clonar e entrar
git clone <url-do-repo>
cd hango

# 2) Virtualenv
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# 3) Dependências
pip install -r requirements.txt

# 4) Migrar
python manage.py migrate

# 5) Superusuário
python manage.py createsuperuser

# 6) Rodar
python manage.py runserver

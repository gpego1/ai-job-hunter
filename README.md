# AI Job Hunter — MVP local

MVP de coleta de vagas Java júnior usando APIs públicas de job boards, FastAPI, PostgreSQL, n8n e Ollama. **Não envia e-mails nem altera seu currículo automaticamente.**

## Requisitos
- Docker Desktop + Docker Compose v2 (Windows com WSL2 habilitado)
- Aproximadamente 8 GB RAM disponíveis para os containers (varia com o modelo Ollama)

## Inicialização
1. Copie `.env.example` para `.env` e substitua as duas senhas/segredos por valores fortes.
2. Edite `config/companies.json` e adicione **tokens reais de job boards** por empresa. O token Greenhouse é o nome em `boards.greenhouse.io/<token>`; o Lever é o nome em `jobs.lever.co/<token>`. Não coloque URLs inteiras.
3. Rode `docker compose up -d --build`.
4. Rode `docker compose exec ollama ollama pull gemma3:1b`.
5. Verifique `http://localhost:8000/health`, `http://localhost:8000/docs` e `http://localhost:5678` (crie a conta de administrador local do n8n).
6. Teste `http://localhost:8000/jobs/search?days=7` e `http://localhost:8000/jobs`.
7. Importe `n8n/workflow.json` pelo editor do n8n e execute manualmente. Requer ao menos um board configurado e modelo Ollama baixado.

## Observações
- Se `companies.json` estiver vazio, a API retorna zero resultados — não é um erro.
- Filtros conservadores: o cargo deve mencionar nível inicial e backend/software e a descrição deve citar Java. Vagas sem data original de publicação são excluídas do filtro de recentes. Isso reduz falsos positivos, mas pode perder oportunidades válidas.
- `requirements_detected` é um conjunto de tecnologias mencionadas, não necessariamente requisitos obrigatórios.
- Dados podem conter texto externo não confiável; não o use como instruções para sistemas com acesso a e-mail.
- Não publique a API, o painel n8n ou Ollama diretamente na internet.
- O workflow demonstra análise estruturada de requisitos em Ollama. Adaptação de currículo e envio só devem ser adicionados após fornecer uma fonte canônica do currículo e implementar revisão/aprovação.
- Se o modelo ficar muito lento, interrompa o Ollama com `docker compose stop ollama` e rode apenas os outros serviços.
- Para desligar mantendo dados: `docker compose down`; **não** use `down -v`, pois remove os volumes.

## Endereços dentro da rede Docker
- API: `http://api:8000`
- Ollama: `http://ollama:11434`
- Postgres: `postgres:5432`

## Documentação
- https://docs.greenhouse.io/job-board
- https://github.com/lever/postings-api
- https://docs.n8n.io/hosting/installation/server-setups/docker-compose/
- https://docs.ollama.com/api

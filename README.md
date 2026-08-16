# Haki Vault — Instagram publisher

Este repositório automatiza o fluxo da página: recebe um URL, descarrega o
vídeo na melhor qualidade disponível, roda clips horizontais 90° para a direita,
converte para 1080×1920, guarda o MP4 num GitHub Release público e publica o
Reel no Instagram sem depender do computador local.

## Configuração única

No repositório, abre **Settings → Secrets and variables → Actions → New
repository secret** e cria:

```text
Name: INSTAGRAM_ACCESS_TOKEN
Value: o teu token do Instagram
```

`GITHUB_TOKEN` já é fornecido automaticamente pelo GitHub Actions. Não deve ser
colocado no código nem no `queue.json`.

Para executar o script diretamente num computador privado, também existe um
fallback local opcional. Cria `scripts/instagram_token.py` com:

```python
ACCESS_TOKEN = "cola-a-chave-aqui"
```

Esse ficheiro está no `.gitignore` e não é enviado para o GitHub. No Actions, o
valor usado continua a ser `INSTAGRAM_ACCESS_TOKEN`.

## Como adicionar vídeos

Adiciona um item à lista de `queue.json`, usando o URL do YouTube ou Instagram e
o título. A descrição é sempre exatamente `RATE THIS 🔥`:

```json
{
  "id": "one-piece-galaxy-impact",
  "url": "https://www.instagram.com/p/EXEMPLO/",
  "title": "One Piece - Galaxy Impact",
  "caption": "RATE THIS 🔥",
  "status": "pending",
  "scheduled_at": null
}
```

O agendamento é feito pela automação Codex **Haki Vault Instagram queue**, que
corre às 12:00, 17:00 e 22:00 no fuso `Europe/Lisbon`, com no máximo três
publicações por dia. O GitHub fica apenas com o código, a fila e os assets
temporários dos vídeos. Quando um item fica pronto, o MP4 é enviado para um
Release público; o URL desse asset é usado pela API do Instagram e fica
registado em `queue.json`. Depois da confirmação da publicação, o Release é
apagado automaticamente.

Para testar manualmente, usa **Actions → Instagram publisher → Run workflow** e
escolhe `auto`, `prepare` ou `publish`. O workflow manual é apenas um fallback;
não cria outro agendamento.

## Estados da fila

`pending` → `preparing` → `ready` → `publishing` → `published`.

Erros ficam como `failed` no item, em `last_error`, para ser fácil corrigir o
URL e reenviar.


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

O workflow verifica a fila a cada 15 minutos. Os horários são 12:00, 17:00 e
22:00 no fuso `Europe/Lisbon`, com no máximo três publicações por dia. Quando
um item fica pronto, o vídeo é enviado para um Release público; o URL desse
asset é usado pela API do Instagram e fica registado em `queue.json`.

Para testar manualmente, usa **Actions → Instagram publisher → Run workflow** e
escolhe `auto`, `prepare` ou `publish`.

## Estados da fila

`pending` → `preparing` → `ready` → `publishing` → `published`.

Erros ficam como `failed` no item, em `last_error`, para ser fácil corrigir o
URL e reenviar.


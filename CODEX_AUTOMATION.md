# Agendamento no Codex

A automação ativa chama-se **Haki Vault Instagram queue**.

## Fluxo simples

1. Abre `queue.json` no GitHub.
2. Adiciona um objeto com `url`, `title`, `status: "pending"` e `scheduled_at: null`.
3. A automação do Codex escolhe o próximo horário livre: 12:00, 17:00 ou 22:00, no fuso de Lisboa.
4. No horário, descarrega, converte, guarda o MP4 temporariamente num Release e publica no Instagram.
5. Consulta `queue.json`: o item passa para `published` e recebe o permalink.
6. O Release temporário é apagado depois da confirmação.

Exemplo:

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

Não é necessário manter o computador ligado para a automação Codex. O GitHub
Actions fica desativado como agenda para evitar publicações duplicadas.


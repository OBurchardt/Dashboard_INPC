// Função da Vercel para /api/chat: toda a lógica está em lib/chat.ts, que o servidor local também usa.
import { responderChat } from "../lib/chat.js";

export default { fetch: (request: Request) => responderChat(request) };

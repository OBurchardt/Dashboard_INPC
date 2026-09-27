// Função da Vercel para /api/estado: o painel pergunta se o chat está disponível e com qual snapshot.
import { estadoDoServico } from "../lib/chat.js";

export default { fetch: () => estadoDoServico() };

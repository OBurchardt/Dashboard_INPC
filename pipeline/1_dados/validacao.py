"""
Etapa: 1.3 Validacao
Faz: roda checagens sobre a base tratada (chaves, continuidade, atualidade, dois canais do INEGI,
agregação temporal, aditividade das incidências, gabarito dos tabulados oficiais, genéricos e
reagregação Laspeyres). Se uma checagem crítica falhar, interrompe o pipeline.
Lê: data/processed/ (series, genericos, ponderadores, hierarquia), data/raw/tabulados/,
    data/raw/revisoes.csv, config/catalogo_series.csv, config/calendario_releases.csv
Escreve: data/processed/relatorio_validacao.json
"""

import json
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))
from config import parametros  # noqa: E402

registro = logging.getLogger("validacao")

FONTE_BIE = "inegi_bie"
FONTE_INDICESDEPRECIOS = "inegi_indicesdeprecios"
MESES_ESPANHOL = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
                  "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}
PADRAO_ROTULO_TABULADO = re.compile(r"^(?:([12])Q )?(" + "|".join(MESES_ESPANHOL) + r") (\d{4})$")
PERCENTUAL = 100


class FalhaDeValidacao(RuntimeError):
    """Uma ou mais checagens críticas falharam; o pipeline deve parar."""


def agora_cidade_do_mexico():
    """Não recebe nada; devolve a data e hora atuais no fuso da Cidade do México."""
    return datetime.now(ZoneInfo(parametros.FUSO_HORARIO))


def normalizar_nome(texto):
    """Recebe um nome; devolve-o sem acento, minúsculo e só com letras e dígitos."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def ler_entradas():
    """Não recebe nada; devolve as tabelas de data/processed, o catálogo e o calendário (config/)."""
    return {
        "series": pd.read_parquet(parametros.ARQUIVO_SERIES),
        "genericos": pd.read_parquet(parametros.ARQUIVO_GENERICOS),
        "ponderadores": pd.read_parquet(parametros.ARQUIVO_PONDERADORES),
        "hierarquia": pd.read_parquet(parametros.ARQUIVO_HIERARQUIA),
        "catalogo": pd.read_csv(parametros.ARQUIVO_CATALOGO, dtype=str, keep_default_na=False),
        "calendario": pd.read_csv(parametros.ARQUIVO_CALENDARIO, dtype=str),
    }


def ordem_temporal(tabela, frequencia):
    """Recebe tabela com ano, mes e quinzena e a frequência; devolve a posição inteira de cada período (passo 1 entre períodos consecutivos)."""
    if frequencia == "mensal":
        return tabela["ano"] * 12 + tabela["mes"] - 1
    return tabela["ano"] * 24 + (tabela["mes"] - 1) * 2 + tabela["quinzena"].astype("int64") - 1


def ordem_de_periodo(periodo):
    """Recebe um período 'AAAA-MM' ou 'AAAA-MM-Qn'; devolve sua posição inteira na frequência correspondente."""
    partes = periodo.split("-")
    ano, mes = int(partes[0]), int(partes[1])
    return ano * 12 + mes - 1 if len(partes) == 2 else ano * 24 + (mes - 1) * 2 + int(partes[2][1]) - 1


def nova_checagem(codigo, nome, descricao, critica, metrica, tolerancia, passou, detalhe, aviso=False):
    """Recebe os campos de uma checagem; devolve o dicionário padronizado com resultado ok/falha/aviso."""
    resultado = "ok" if passou else ("aviso" if aviso else "falha")
    return {"codigo": codigo, "nome": nome, "descricao": descricao, "critica": critica, "resultado": resultado,
            "metrica": None if metrica is None or (isinstance(metrica, float) and np.isnan(metrica)) else float(metrica),
            "tolerancia": tolerancia, "detalhe": detalhe}


def series_principais(series, tipo):
    """Recebe series.parquet e o tipo; devolve só as séries principais (app indicesdeprecios) desse tipo."""
    return series[(series["uso"] == "principal") & (series["tipo"] == tipo)]


def checar_chaves(series, genericos):
    """C1. Recebe séries e genéricos; devolve a checagem de chaves únicas e sem nulo."""
    chave_series = ["fonte", "id_serie", "periodo"]
    chave_genericos = ["codigo_generico", "frequencia", "periodo"]
    problemas = {
        "series_duplicadas": int(series.duplicated(chave_series).sum()),
        "series_chave_nula": int(series[chave_series].isna().any(axis=1).sum()),
        "genericos_duplicados": int(genericos.duplicated(chave_genericos).sum()),
        "genericos_chave_nula": int(genericos[chave_genericos].isna().any(axis=1).sum()),
    }
    total = sum(problemas.values())
    return nova_checagem("C1", "chaves", "Chaves únicas e sem nulo em (fonte, id_serie, periodo) e (codigo_generico, frequencia, periodo)",
                         True, total, 0, total == 0, problemas)


def checar_continuidade(series):
    """C2. Recebe séries; devolve a checagem de que nenhuma série principal tem período faltando ou nulo (fora das ausências oficiais)."""
    lacunas = []
    for (id_serie, tipo, frequencia), grupo in series[series["uso"] == "principal"].groupby(["id_serie", "tipo", "frequencia"]):
        grupo = grupo.sort_values("data")
        passos = ordem_temporal(grupo, frequencia).diff().dropna()
        faltando = int((passos - 1).clip(lower=0).sum())
        oficiais = set(parametros.AUSENCIAS_OFICIAIS.get((tipo, frequencia), []))
        nulos = grupo[grupo["valor"].isna() & ~grupo["periodo"].isin(oficiais)]["periodo"].tolist()
        if faltando or nulos:
            lacunas.append({"id_serie": id_serie, "periodos_faltando": faltando, "nulos": nulos[:5]})
    total = sum(item["periodos_faltando"] + len(item["nulos"]) for item in lacunas)
    return nova_checagem("C2", "continuidade", "Séries principais sem período faltando entre o primeiro e o último (ausências oficiais do INEGI à parte)",
                         True, total, 0, total == 0, {"series_com_lacuna": lacunas[:10], "ausencias_oficiais": {
                             f"{tipo} {frequencia}": periodos for (tipo, frequencia), periodos in parametros.AUSENCIAS_OFICIAIS.items()}})


def periodos_esperados(calendario, agora):
    """Recebe o calendário e o momento atual; devolve {frequencia: último período que os releases já ocorridos publicaram}."""
    esperados = {}
    for _, release in calendario.iterrows():
        momento = datetime.fromisoformat(f"{release['data_divulgacao']}T{release['hora_local']}").replace(tzinfo=ZoneInfo(release["fuso"]))
        if momento > agora:
            continue
        referencia = release["periodo_referencia"]
        novos = {"quinzenal": f"{referencia}-Q1"} if release["tipo"] == "1a_quinzena" else {"mensal": referencia, "quinzenal": f"{referencia}-Q2"}
        for frequencia, periodo in novos.items():
            if frequencia not in esperados or ordem_de_periodo(periodo) > ordem_de_periodo(esperados[frequencia]):
                esperados[frequencia] = periodo
    return esperados


def checar_atualidade(series, calendario, agora):
    """C3. Recebe séries, calendário e momento atual; devolve a checagem de que o último período das séries principais é o esperado pelo calendário."""
    esperados = periodos_esperados(calendario, agora)
    principais = series[(series["uso"] == "principal") & series["valor"].notna()]
    ultimos = principais.sort_values("data").groupby(["id_serie", "frequencia"])["periodo"].last().reset_index()
    ultimos["esperado"] = ultimos["frequencia"].map(esperados)
    atrasadas = ultimos[ultimos["periodo"] != ultimos["esperado"]]
    return nova_checagem("C3", "atualidade", "Último período das séries principais = o esperado pelos releases já ocorridos",
                         True, len(atrasadas), 0, atrasadas.empty,
                         {"esperado": esperados, "divergentes": atrasadas.head(10).to_dict("records")})


def checar_dois_canais(series, tipo, tolerancia, codigo):
    """C4. Recebe séries, tipo e tolerância; devolve a checagem app indicesdeprecios vs API BIE em toda a história comum dos agregados."""
    chave = ["tipo", "frequencia", "componente", "periodo"]
    app = series[(series["fonte"] == FONTE_INDICESDEPRECIOS) & (series["tipo"] == tipo)][chave + ["valor"]]
    bie = series[(series["fonte"] == FONTE_BIE) & (series["tipo"] == tipo)][chave + ["valor"]]
    juntos = app.merge(bie, on=chave, suffixes=("_app", "_bie")).dropna(subset=["valor_app", "valor_bie"])
    juntos["desvio"] = (juntos["valor_app"] - juntos["valor_bie"]).abs()
    pior = juntos.loc[juntos["desvio"].idxmax()] if len(juntos) else None
    metrica = float(juntos["desvio"].max()) if len(juntos) else np.nan
    detalhe = {"pares_comparados": len(juntos), "series_comparadas": juntos.groupby(["frequencia", "componente"]).ngroups,
               "pior": None if pior is None else {campo: str(pior[campo]) for campo in ["frequencia", "componente", "periodo", "valor_app", "valor_bie"]}}
    return nova_checagem(codigo, f"dois canais ({tipo})", f"App vs BIE para os agregados ({tipo}), toda a história comum",
                         True, metrica, tolerancia, len(juntos) > 0 and metrica <= tolerancia, detalhe)


def checar_agregacao_temporal(series):
    """C5. Recebe séries; devolve a checagem de que o índice mensal = média simples das duas quinzenas, para os 16 componentes desde 1988."""
    indices = series_principais(series, "indice")
    indices = indices[indices["ano"] >= parametros.ANO_INICIO_AGREGACAO_TEMPORAL]
    quinzenas = indices[indices["frequencia"] == "quinzenal"].groupby(["componente", "ano", "mes"]).agg(media=("valor", "mean"), n=("valor", "count"))
    mensal = indices[indices["frequencia"] == "mensal"].set_index(["componente", "ano", "mes"])["valor"]
    juntos = quinzenas[quinzenas["n"] == 2].join(mensal, how="inner").dropna().reset_index()
    juntos["desvio"] = (juntos["valor"] - juntos["media"]).abs()
    juntos["ordem"] = juntos["ano"] * 12 + juntos["mes"] - 1
    corte = ordem_de_periodo(parametros.PERIODO_INICIO_AGREGACAO_TEMPORAL_COMPONENTES)
    avaliados = juntos[(juntos["componente"] == "indice_general") | (juntos["ordem"] >= corte)]
    fora = juntos.drop(avaliados.index)
    pior = avaliados.loc[avaliados["desvio"].idxmax()]
    return nova_checagem("C5", "agregação temporal", "Índice mensal = média das duas quinzenas (INPC geral desde 1988; demais 15 componentes "
                         f"desde {parametros.PERIODO_INICIO_AGREGACAO_TEMPORAL_COMPONENTES})",
                         True, avaliados["desvio"].max(), parametros.TOLERANCIA_AGREGACAO_TEMPORAL,
                         avaliados["desvio"].max() <= parametros.TOLERANCIA_AGREGACAO_TEMPORAL,
                         {"meses_comparados": len(avaliados), "pior": {"componente": pior["componente"], "periodo": f"{pior['ano']}-{pior['mes']:02d}"},
                          "fora_do_corte": {"meses": len(fora), "desvio_maximo": float(fora["desvio"].max()) if len(fora) else None}})


def variacao_do_indice_geral(series, frequencia):
    """Recebe séries e frequência; devolve a variação percentual do INPC geral (app) em relação ao período imediatamente anterior."""
    geral = series_principais(series, "indice")
    geral = geral[(geral["frequencia"] == frequencia) & (geral["nivel"] == 0)].sort_values("data").copy()
    geral["ordem"] = ordem_temporal(geral, frequencia)
    anterior = geral["valor"].shift(1).where(geral["ordem"].diff() == 1)
    return pd.Series(((geral["valor"] / anterior - 1) * PERCENTUAL).values, index=geral["periodo"].values)


def checar_aditividade(series):
    """C6. Recebe séries; devolve a checagem de que as incidências de cada nível (1, 2 e 3) somam a variação do INPC geral, desde 2002."""
    incidencias = series_principais(series, "incidencia")
    incidencias = incidencias[incidencias["ano"] >= parametros.ANO_INICIO_ADITIVIDADE]
    piores, periodos, excluidos = [], 0, []
    for frequencia in ("mensal", "quinzenal"):
        variacao = variacao_do_indice_geral(series, frequencia)
        da_frequencia = incidencias[incidencias["frequencia"] == frequencia]
        fora = parametros.PERIODOS_EXCLUIDOS_ADITIVIDADE.get(frequencia, [])
        for nivel in (1, 2, 3):
            tabela = da_frequencia[da_frequencia["nivel"] == nivel].pivot(index="periodo", columns="componente", values="valor").dropna()
            soma = tabela.sum(axis=1)
            desvio = (soma - variacao.reindex(soma.index)).abs().dropna()
            excluidos += [{"frequencia": frequencia, "nivel": nivel, "periodo": periodo, "desvio": float(desvio[periodo])}
                          for periodo in fora if periodo in desvio.index]
            desvio = desvio.drop([periodo for periodo in fora if periodo in desvio.index])
            periodos += len(desvio)
            if len(desvio):
                piores.append({"frequencia": frequencia, "nivel": nivel, "desvio": float(desvio.max()), "periodo": desvio.idxmax(),
                               "componentes": tabela.shape[1]})
    pior = max(piores, key=lambda item: item["desvio"])
    return nova_checagem("C6", "aditividade das incidências", "Soma das incidências dos níveis 1, 2 e 3 = variação do INPC geral (desde 2002)",
                         True, pior["desvio"], parametros.TOLERANCIA_ADITIVIDADE_PONTOS,
                         pior["desvio"] <= parametros.TOLERANCIA_ADITIVIDADE_PONTOS, {"pior": pior, "por_particao": piores,
                                                                                     "periodos_comparados": periodos,
                                                                                     "periodos_excluidos": excluidos})


def periodo_do_tabulado(rotulo):
    """Recebe o rótulo de período de um tabulado (' Ago 2026', '1Q Sep 2026'); devolve 'AAAA-MM' ou 'AAAA-MM-Qn'."""
    encontrado = PADRAO_ROTULO_TABULADO.match(rotulo.strip())
    if not encontrado:
        raise ValueError(f"Rótulo de período de tabulado inesperado: {rotulo!r}")
    quinzena, mes, ano = encontrado.groups()
    return f"{ano}-{MESES_ESPANHOL[mes]:02d}" + (f"-Q{quinzena}" if quinzena else "")


def checar_gabarito(series, catalogo):
    """C7. Recebe séries e catálogo; devolve a checagem de variação, variação anual e incidência dos 16 componentes contra os tabulados CA55/CA56 (último e penúltimo período)."""
    componente_por_nome = {normalizar_nome(nome): componente for nome, componente in
                           catalogo[catalogo["fonte"] == FONTE_INDICESDEPRECIOS][["nome", "componente"]].drop_duplicates().values}
    comparacoes, pior = [], None
    for frequencia, cuadro in parametros.TABULADOS_OFICIAIS.items():
        indices = series_principais(series, "indice")
        indices = indices[indices["frequencia"] == frequencia].copy()
        indices["ordem"] = ordem_temporal(indices, frequencia)
        nivel_por_ordem = indices.set_index(["componente", "ordem"])["valor"]
        incidencias = series_principais(series, "incidencia")
        incidencia = incidencias[incidencias["frequencia"] == frequencia].set_index(["componente", "periodo"])["valor"]
        for esquema in parametros.ESQUEMAS_TABULADO.values():
            caminho = parametros.PASTA_RAW / "tabulados" / f"{cuadro}_esquema{esquema}.json"
            tabulado = json.loads(caminho.read_text(encoding="utf-8"))
            periodo = periodo_do_tabulado(tabulado["Encab"][0]["periodo_actual"])
            ordem = ordem_de_periodo(periodo)
            for linha in tabulado["Datos"]:
                componente = componente_por_nome.get(normalizar_nome(linha["descripcion"]))
                if componente is None:
                    raise ValueError(f"{caminho.name}: componente não reconhecido {linha['descripcion']!r}")
                atual = nivel_por_ordem.get((componente, ordem))
                anterior = nivel_por_ordem.get((componente, ordem - 1))
                ano_antes = nivel_por_ordem.get((componente, ordem - parametros.PERIODOS_POR_ANO[frequencia]))
                calculado = {
                    "variacao": None if atual is None or anterior is None else (atual / anterior - 1) * PERCENTUAL,
                    "variacao_anual": None if atual is None or ano_antes is None else (atual / ano_antes - 1) * PERCENTUAL,
                    "incidencia": incidencia.get((componente, periodo)),
                }
                oficial = {"variacao": linha["valor_mensual"], "variacao_anual": linha["valor_anual"], "incidencia": linha["valor_incidencia"]}
                for medida, valor in calculado.items():
                    desvio = np.inf if valor is None or pd.isna(valor) else abs(valor - float(oficial[medida]))
                    item = {"cuadro": cuadro, "periodo": periodo, "componente": componente, "medida": medida,
                            "base": None if valor is None or pd.isna(valor) else round(float(valor), 4), "oficial": oficial[medida], "desvio": desvio}
                    comparacoes.append(item)
                    if pior is None or desvio > pior["desvio"]:
                        pior = item
    metrica = max(item["desvio"] for item in comparacoes)
    periodos = sorted({f"{item['cuadro']} {item['periodo']}" for item in comparacoes})
    return nova_checagem("C7", "gabarito oficial", "Variação, variação anual e incidência dos 16 componentes = tabulados CA55/CA56 (último e penúltimo período)",
                         True, metrica, parametros.TOLERANCIA_GABARITO_PONTOS, metrica <= parametros.TOLERANCIA_GABARITO_PONTOS,
                         {"comparacoes": len(comparacoes), "periodos": periodos,
                          "pior": {**pior, "desvio": None if np.isinf(pior["desvio"]) else pior["desvio"]}})


def checar_genericos(genericos, ponderadores):
    """C8. Recebe genéricos e ponderadores; devolve a checagem de 292 genéricos com série nas duas frequências, classificação única e ponderadores somando 100."""
    com_serie = genericos[genericos["indice"].notna()].groupby("frequencia")["codigo_generico"].nunique().to_dict()
    vigente = ponderadores[ponderadores["cesta"] == parametros.CESTA_VIGENTE]
    mal_classificados = vigente[vigente["subindice"].isna() | vigente["subindice"].str.contains(r"\|")]["nome_generico"].tolist()
    somas = ponderadores.groupby("cesta")["ponderador"].sum().to_dict()
    desvio_soma = max(abs(soma - parametros.SOMA_PONDERADORES_ESPERADA) for soma in somas.values())
    passou = (all(com_serie.get(frequencia) == parametros.NUMERO_GENERICOS_ESPERADO for frequencia in parametros.ARVORES_GENERICOS)
              and len(vigente) == parametros.NUMERO_GENERICOS_ESPERADO and not mal_classificados
              and desvio_soma <= parametros.TOLERANCIA_SOMA_PONDERADORES)
    return nova_checagem("C8", "genéricos", "292 genéricos com série nas duas frequências, um subíndice cada, ponderadores de cada cesta somam 100",
                         True, desvio_soma, parametros.TOLERANCIA_SOMA_PONDERADORES, passou,
                         {"genericos_com_serie": com_serie, "genericos_cesta_vigente": len(vigente),
                          "mal_classificados": mal_classificados, "soma_por_cesta": somas})


def checar_reagregacao(series, genericos, ponderadores, hierarquia):
    """C9. Recebe séries, genéricos, ponderadores e hierarquia; devolve a checagem de que a agregação Laspeyres encadeada dos genéricos reproduz o INPC e os 9 subíndices."""
    vigente = ponderadores[ponderadores["cesta"] == parametros.CESTA_VIGENTE].set_index("codigo_generico")
    fator_componente = hierarquia[hierarquia["tipo_no"] == "componente"].set_index("id_no")["fator_encadeamento_2024"]
    subindices = hierarquia[(hierarquia["tipo_no"] == "componente") & (hierarquia["nivel"] == 3)]["id_no"].tolist()
    indices = series_principais(series, "indice")
    resultados = []
    for frequencia, inicio in parametros.PERIODO_INICIO_REAGREGACAO.items():
        dados = genericos[genericos["frequencia"] == frequencia].copy()
        dados["ordem"] = ordem_temporal(dados, frequencia)
        dados = dados[dados["ordem"] >= ordem_de_periodo(inicio)]
        relativos = dados.pivot(index="periodo", columns="codigo_generico", values="indice")
        relativos = relativos.divide(vigente["fator_encadeamento"].reindex(relativos.columns), axis=1)
        oficiais = indices[indices["frequencia"] == frequencia].pivot(index="periodo", columns="componente", values="valor")
        for agregado in ["indice_general", *subindices]:
            membros = vigente.index.tolist() if agregado == "indice_general" else vigente.index[vigente["subindice"] == agregado].tolist()
            pesos = vigente.loc[membros, "ponderador"]
            estimado = fator_componente[agregado] * (relativos[membros] * pesos).sum(axis=1, min_count=len(membros)) / pesos.sum()
            desvio = ((estimado / oficiais[agregado].reindex(estimado.index) - 1).abs() * PERCENTUAL)
            resultados.append({"frequencia": frequencia, "agregado": agregado, "genericos": len(membros), "periodos": int(desvio.notna().sum()),
                               "desvio_maximo": float(desvio.max()) if desvio.notna().all() else np.inf,
                               "periodo": desvio.idxmax() if desvio.notna().all() else "valor ausente"})
    pior = max(resultados, key=lambda item: item["desvio_maximo"])
    return nova_checagem("C9", "reagregação Laspeyres", "Genéricos × ponderadores 2024 com fator de encadeamento oficial reproduzem INPC e 9 subíndices",
                         True, pior["desvio_maximo"], parametros.TOLERANCIA_REAGREGACAO_PERCENTUAL,
                         pior["desvio_maximo"] <= parametros.TOLERANCIA_REAGREGACAO_PERCENTUAL,
                         {"pior": {**pior, "desvio_maximo": None if np.isinf(pior["desvio_maximo"]) else pior["desvio_maximo"]},
                          "por_agregado": resultados})


def checar_revisoes(relatorio_anterior):
    """A1. Recebe o relatório anterior (ou None); devolve o aviso com as revisões de data/raw/revisoes.csv registradas desde a última validação."""
    caminho = parametros.PASTA_RAW / parametros.NOME_REVISOES
    revisoes = pd.read_csv(caminho, dtype=str) if caminho.exists() else pd.DataFrame(columns=["data_deteccao"])
    if relatorio_anterior and len(revisoes):
        limite = datetime.fromisoformat(relatorio_anterior["gerado_em"])
        revisoes = revisoes[pd.to_datetime(revisoes["data_deteccao"]).map(lambda momento: momento.to_pydatetime() > limite)]
    return nova_checagem("A1", "revisões", "Revisões registradas pela ingestão desde a última validação", False, len(revisoes), 0,
                         revisoes.empty, {"revisoes": revisoes.head(20).to_dict("records")}, aviso=True)


def checar_historico_curto(genericos):
    """A2. Recebe genéricos; devolve o aviso com os genéricos cujo índice começa na cesta 2024 (histórico curto)."""
    inicio_cesta = pd.Timestamp(parametros.CESTAS[parametros.CESTA_VIGENTE]["vigencia_inicio"][:7] + "-01")
    primeiros = genericos[genericos["indice"].notna()].groupby(["codigo_generico", "nome_generico"])["data"].min()
    curtos = primeiros[primeiros >= inicio_cesta]
    lista = [f"{codigo} {nome} (desde {data:%Y-%m})" for (codigo, nome), data in curtos.items()]
    return nova_checagem("A2", "histórico curto", "Genéricos criados na cesta 2024, sem histórico anterior", False, len(lista), 0,
                         not lista, {"genericos": lista}, aviso=True)


def checar_nulos_genericos(genericos):
    """A3. Recebe genéricos; devolve o aviso com os genéricos que têm valores ausentes no meio da série."""
    nulos = genericos[genericos["indice"].isna()]
    resumo = nulos.groupby(["codigo_generico", "nome_generico", "frequencia"])["periodo"].agg(["count", "min", "max"]).reset_index()
    lista = [f"{linha.codigo_generico} {linha.nome_generico} ({linha.frequencia}): {linha['count']} nulo(s) entre {linha['min']} e {linha['max']}"
             for _, linha in resumo.iterrows()]
    return nova_checagem("A3", "nulos em genéricos", "Genéricos com valores ausentes no meio da série", False, len(nulos), 0,
                         not lista, {"genericos": lista}, aviso=True)


def imprimir_tabela(checagens):
    """Recebe a lista de checagens; imprime no terminal a tabela checagem | resultado | desvio máximo | tolerância. Não devolve nada."""
    registro.info("  %-34s %-7s %14s %12s", "checagem", "result.", "desvio máximo", "tolerância")
    for checagem in checagens:
        metrica = "-" if checagem["metrica"] is None else (f"{checagem['metrica']:.6g}" if not np.isinf(checagem["metrica"]) else "inf")
        registro.info("  %-34s %-7s %14s %12s", f"{checagem['codigo']} {checagem['nome']}"[:34], checagem["resultado"], metrica,
                      checagem["tolerancia"])


def executar():
    """Não recebe nada; roda todas as checagens, grava relatorio_validacao.json e devolve o relatório; levanta FalhaDeValidacao se uma crítica falhar."""
    inicio = time.time()
    agora = agora_cidade_do_mexico()
    entradas = ler_entradas()
    series, genericos = entradas["series"], entradas["genericos"]
    caminho_relatorio = parametros.ARQUIVO_RELATORIO_VALIDACAO
    relatorio_anterior = json.loads(caminho_relatorio.read_text(encoding="utf-8")) if caminho_relatorio.exists() else None

    checagens = [
        checar_chaves(series, genericos),
        checar_continuidade(series),
        checar_atualidade(series, entradas["calendario"], agora),
        checar_dois_canais(series, "indice", parametros.TOLERANCIA_DOIS_CANAIS_INDICE, "C4a"),
        checar_dois_canais(series, "incidencia", parametros.TOLERANCIA_DOIS_CANAIS_INCIDENCIA, "C4b"),
        checar_agregacao_temporal(series),
        checar_aditividade(series),
        checar_gabarito(series, entradas["catalogo"]),
        checar_genericos(genericos, entradas["ponderadores"]),
        checar_reagregacao(series, genericos, entradas["ponderadores"], entradas["hierarquia"]),
        checar_revisoes(relatorio_anterior),
        checar_historico_curto(genericos),
        checar_nulos_genericos(genericos),
    ]
    principais = series[(series["uso"] == "principal") & series["valor"].notna()]
    ultimo = principais.sort_values("data").groupby("frequencia")["periodo"].last().to_dict()
    falhas = [checagem for checagem in checagens if checagem["critica"] and checagem["resultado"] == "falha"]
    relatorio = {"gerado_em": agora.isoformat(timespec="seconds"), "status": "falha" if falhas else "ok",
                 "ultimo_periodo_validado": ultimo, "checagens": checagens}
    caminho_relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    imprimir_tabela(checagens)
    registro.info("Validação %s em %.1f s (último período: %s)", relatorio["status"], time.time() - inicio, ultimo)
    if falhas:
        raise FalhaDeValidacao("Checagens críticas falharam: " + "; ".join(
            f"{checagem['codigo']} {checagem['nome']} (desvio {checagem['metrica']}, tolerância {checagem['tolerancia']}; {checagem['detalhe'].get('pior', '')})"
            for checagem in falhas) + ". Pipeline interrompido; veja data/processed/relatorio_validacao.json.")
    return relatorio


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    relatorio_validacao = executar()

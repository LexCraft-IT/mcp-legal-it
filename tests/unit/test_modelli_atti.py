"""Tests for the modelli_atti catalog and genera_modello_atto dispatcher."""

import json
from pathlib import Path

from mcp_legal_it.tools.modelli_atti import genera_modello_atto, lista_categorie_atti, _CATALOGO


# ---------------------------------------------------------------------------
# Catalog data integrity
# ---------------------------------------------------------------------------

class TestCatalogoIntegrity:
    def test_catalog_has_entries(self):
        assert len(_CATALOGO) >= 90, f"Expected >=90 entries, got {len(_CATALOGO)}"

    def test_all_entries_have_required_fields(self):
        required = {"categoria", "descrizione", "tier", "routing",
                     "campi_obbligatori", "riferimenti_normativi"}
        for tipo, entry in _CATALOGO.items():
            missing = required - set(entry.keys())
            assert not missing, f"{tipo} missing fields: {missing}"

    def test_all_tiers_are_valid(self):
        for tipo, entry in _CATALOGO.items():
            assert entry["tier"] in (1, 2, 3, 4), f"{tipo} has invalid tier: {entry['tier']}"

    def test_all_routing_types_are_valid(self):
        valid_types = {"tool_diretto", "tool_enhance", "resource", "preventivo_procedura"}
        for tipo, entry in _CATALOGO.items():
            rt = entry["routing"]["tipo"]
            assert rt in valid_types, f"{tipo} has invalid routing type: {rt}"

    def test_tier1_entries_have_tool_diretto(self):
        for tipo, entry in _CATALOGO.items():
            if entry["tier"] == 1:
                assert entry["routing"]["tipo"] == "tool_diretto", (
                    f"Tier 1 entry {tipo} should have routing.tipo=tool_diretto"
                )

    def test_tier3_entries_have_resource(self):
        for tipo, entry in _CATALOGO.items():
            if entry["tier"] == 3:
                assert entry["routing"]["tipo"] == "resource", (
                    f"Tier 3 entry {tipo} should have routing.tipo=resource"
                )
                assert "resource" in entry["routing"], (
                    f"Tier 3 entry {tipo} missing routing.resource"
                )

    def test_tier4_entries_have_preventivo_procedura(self):
        for tipo, entry in _CATALOGO.items():
            if entry["tier"] == 4:
                assert entry["routing"]["tipo"] == "preventivo_procedura", (
                    f"Tier 4 entry {tipo} should have routing.tipo=preventivo_procedura"
                )

    def test_categories_are_consistent(self):
        cats = {v["categoria"] for v in _CATALOGO.values()}
        expected_cats = {
            "atti_introduttivi", "esecuzione", "notifiche", "attestazioni",
            "procure", "stragiudiziale", "istanze", "pct", "preventivi", "privacy",
        }
        assert cats == expected_cats, f"Unexpected categories: {cats - expected_cats}"

    def test_json_file_matches_loaded_data(self):
        """Every record in the file reaches the catalogue, and nothing else does.

        The loader drops `_`-prefixed keys because those carry the table's
        vintage (see mcp_legal_it/lib/_data.py), not an atto. Comparing raw lengths would
        now fail for a reason that has nothing to do with a missing model.
        """
        data_path = Path(__file__).resolve().parent.parent.parent / "plugin" / "server" / "mcp_legal_it" / "data" / "modelli_atti.json"
        with open(data_path) as f:
            raw = json.load(f)
        records = {k for k in raw if not k.startswith("_")}
        assert records == set(_CATALOGO)


# ---------------------------------------------------------------------------
# genera_modello_atto — catalog mode
# ---------------------------------------------------------------------------

class TestGeneraModelloAttoCatalogo:
    def test_catalogo_returns_all_entries(self):
        result = genera_modello_atto(tipo_atto="catalogo")
        assert "totale_tipi" in result
        assert result["totale_tipi"] == len(_CATALOGO)
        assert "categorie" in result
        assert "catalogo" in result

    def test_catalogo_grouped_by_category(self):
        result = genera_modello_atto(tipo_atto="catalogo")
        total = sum(len(items) for items in result["catalogo"].values())
        assert total == result["totale_tipi"]


# ---------------------------------------------------------------------------
# genera_modello_atto — search mode
# ---------------------------------------------------------------------------

class TestGeneraModelloAttoCerca:
    def test_search_by_keyword(self):
        result = genera_modello_atto(tipo_atto="cerca", parametri={"query": "ingiuntivo"})
        assert result["totale"] > 0
        assert all("ingiuntivo" in r["tipo_atto"] or "ingiuntivo" in r["descrizione"].lower()
                    for r in result["risultati"])

    def test_search_by_norma(self):
        result = genera_modello_atto(tipo_atto="cerca", parametri={"query": "633"})
        assert result["totale"] > 0

    def test_search_no_results(self):
        result = genera_modello_atto(tipo_atto="cerca", parametri={"query": "xyznonexistent"})
        assert result["totale"] == 0

    def test_search_empty_query(self):
        result = genera_modello_atto(tipo_atto="cerca", parametri={})
        assert "errore" in result


# ---------------------------------------------------------------------------
# genera_modello_atto — specific type lookup
# ---------------------------------------------------------------------------

class TestGeneraModelloAttoLookup:
    def test_tier1_tool_diretto(self):
        result = genera_modello_atto(tipo_atto="decreto_ingiuntivo_ordinario")
        assert result["tipo_atto"] == "decreto_ingiuntivo_ordinario"
        assert result["tool_diretto"] == "decreto_ingiuntivo"
        assert result["parametri_fissi"]["tipo_credito"] == "ordinario"
        assert "istruzioni" in result
        assert len(result["campi_obbligatori"]) > 0

    def test_tier2_tool_enhance(self):
        result = genera_modello_atto(tipo_atto="decreto_ingiuntivo_fatture")
        assert result["tool_diretto"] == "decreto_ingiuntivo"
        assert "disponibile_da_fase" in result
        assert result["disponibile_da_fase"] == 2

    def test_tier3_resource(self):
        result = genera_modello_atto(tipo_atto="citazione_ordinaria")
        assert result["resource_modello"] == "legal://riferimenti/modelli-atti-catalogo"
        assert "disponibile_da_fase" in result
        # #195: the answer no longer says the resource is "not yet available" and no longer
        # promises a per-type text model that does not exist.
        assert "non ancora disponibile" not in result["istruzioni"]
        assert "Nessun modello testuale" in result["istruzioni"]

    def test_tier4_preventivo(self):
        result = genera_modello_atto(tipo_atto="preventivo_mediazione")
        # preventivo_procedura non è ancora implementato: si instrada al fallback reale preventivo_civile.
        assert result["tool_diretto"] == "preventivo_civile"
        assert result["tool_non_ancora_disponibile"] == "preventivo_procedura"
        assert "disponibile_da_fase" in result
        assert result["disponibile_da_fase"] == 4

    def test_unknown_type_returns_error(self):
        result = genera_modello_atto(tipo_atto="atto_inesistente_xyz")
        assert "errore" in result
        assert "suggerimenti" in result

    def test_fuzzy_match(self):
        result = genera_modello_atto(tipo_atto="precetto")
        # Should fuzzy-match to atto_di_precetto
        if "errore" in result:
            assert len(result["suggerimenti"]) > 0
        else:
            assert "tipo_atto" in result

    def test_campi_mancanti_without_params(self):
        result = genera_modello_atto(tipo_atto="decreto_ingiuntivo_ordinario")
        assert result["campi_mancanti"] == result["campi_obbligatori"]

    def test_campi_mancanti_with_partial_params(self):
        result = genera_modello_atto(
            tipo_atto="decreto_ingiuntivo_ordinario",
            parametri={"creditore": "Rossi Srl", "debitore": "Bianchi Srl"}
        )
        assert "importo" in result["campi_mancanti"]
        assert "creditore" not in result["campi_mancanti"]

    def test_campi_mancanti_all_provided(self):
        result = genera_modello_atto(
            tipo_atto="decreto_ingiuntivo_ordinario",
            parametri={"creditore": "A", "debitore": "B", "importo": 10000}
        )
        assert result["campi_mancanti"] == []

    def test_all_types_return_valid_routing(self):
        """Every catalog entry must produce a valid result with routing info."""
        for tipo in _CATALOGO:
            result = genera_modello_atto(tipo_atto=tipo)
            assert "errore" not in result, f"{tipo} returned error: {result.get('errore')}"
            has_routing = (
                "tool_diretto" in result
                or "resource_modello" in result
            )
            assert has_routing, f"{tipo} missing routing info"


# ---------------------------------------------------------------------------
# lista_categorie_atti
# ---------------------------------------------------------------------------

class TestListaCategorieAtti:
    def test_returns_all_categories(self):
        result = lista_categorie_atti()
        assert "categorie" in result
        assert result["totale_atti"] == len(_CATALOGO)

    def test_categories_have_counts(self):
        result = lista_categorie_atti()
        total = sum(c["totale"] for c in result["categorie"])
        assert total == result["totale_atti"]

    def test_sorted_by_count_descending(self):
        result = lista_categorie_atti()
        counts = [c["totale"] for c in result["categorie"]]
        assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# Cross-reference: tool names in catalog exist in the server
# ---------------------------------------------------------------------------

class TestCrossReference:
    """Verify that tool names referenced in the catalog are plausible."""

    _KNOWN_TOOLS = {
        "decreto_ingiuntivo", "atto_di_precetto", "sfratto_morosita",
        "sollecito_pagamento", "nota_precisazione_credito", "dichiarazione_553_cpc",
        "procura_alle_liti", "attestazione_conformita", "relata_notifica_pec",
        "preventivo_civile", "preventivo_stragiudiziale", "preventivo_volontaria_giurisdizione",
        "contributo_unificato", "parcella_avvocato_civile", "parcella_avvocato_penale",
        "interessi_legali", "interessi_mora", "rivalutazione_monetaria",
        "interessi_corso_causa", "interessi_acconti", "modello_notula",
        "scadenza_processuale", "scadenze_impugnazioni", "pignoramento_stipendio",
        "conta_giorni", "calcolo_hash", "calcolo_valore_catastale",
        "spese_mediazione", "compenso_ctu", "variazioni_istat",
        "genera_informativa_privacy", "genera_informativa_cookie",
        "genera_informativa_dipendenti", "genera_informativa_videosorveglianza",
        "genera_dpa", "genera_registro_trattamenti", "genera_dpia",
        "genera_notifica_data_breach", "valutazione_data_breach",
        # Future tools
        "preventivo_procedura",
    }

    def test_tier1_tools_exist(self):
        for tipo, entry in _CATALOGO.items():
            if entry["tier"] == 1:
                tool = entry["routing"]["tool"]
                assert tool in self._KNOWN_TOOLS, (
                    f"Tier 1 {tipo} references unknown tool: {tool}"
                )

    def test_calcolo_tools_are_known(self):
        for tipo, entry in _CATALOGO.items():
            for tool in entry.get("tool_calcolo", []):
                assert tool in self._KNOWN_TOOLS, (
                    f"{tipo} references unknown calcolo tool: {tool}"
                )


class TestRouteSulServer:
    """#195: every name a route gives the model must exist on the server it talks to."""

    @staticmethod
    def _superficie():
        import asyncio

        from fastmcp import Client
        from mcp_legal_it.server import mcp

        async def run():
            async with Client(mcp) as c:
                return await c.list_tools(), await c.list_resources()

        tools, resources = asyncio.run(run())
        return {t.name for t in tools}, {str(r.uri) for r in resources}

    def test_route_nominano_risorse_e_tool_registrati(self, monkeypatch):
        monkeypatch.setenv("LEGAL_BROCARDI", "on")
        tools, resources = self._superficie()
        for tipo, entry in _CATALOGO.items():
            routing = entry["routing"]
            if "resource" in routing:
                assert routing["resource"] in resources, f"{tipo}: resource non registrata {routing['resource']}"
            if routing["tipo"] in ("tool_diretto", "tool_enhance"):
                assert routing["tool"] in tools, f"{tipo}: tool non registrato {routing['tool']}"
            for tool in entry.get("tool_calcolo", []):
                assert tool in tools, f"{tipo}: tool_calcolo non registrato {tool}"


# ---------------------------------------------------------------------------
# Riferimenti normativi riletti sul testo vigente (benchmark fase 3)
# ---------------------------------------------------------------------------

class TestCatalogoNormeVigenti:
    def test_attestazioni_citano_artt_196_disp_att_cpc(self):
        # D.Lgs. 149/2022 art. 11 abroga artt. 16-bis e 16-undecies DL 179/2012; le attestazioni
        # sono negli artt. 196-octies..196-undecies disp. att. c.p.c. (procedimenti dal 28/02/2023,
        # art. 35 co. 1 D.Lgs. 149/2022)
        r = genera_modello_atto("attestazione_copia_informatica")
        rif = " ".join(r["riferimenti_normativi"])
        assert "196-undecies" in rif and "196-novies" in rif and "196-decies" in rif
        assert "16-bis" not in rif
        assert any("28/02/2023" in a for a in r["avvertenze"])

    def test_cerca_196_octies_trova_le_attestazioni(self):
        r = genera_modello_atto("cerca", {"query": "196-octies"})
        assert r["totale"] >= 1

    def test_nessuna_voce_richiede_la_formula_esecutiva(self):
        # art. 475 c.p.c.: titolo in copia attestata conforme o duplicato informatico
        for tipo, e in _CATALOGO.items():
            testo = " ".join([e["descrizione"], *e.get("avvertenze", [])]).lower()
            assert "formula esecutiva" not in testo, tipo

    def test_appello_appellato_20_giorni_art_347(self):
        # art. 347 co. 1 c.p.c. (D.Lgs. 164/2024): almeno venti giorni prima dell'udienza
        avv = " ".join(_CATALOGO["atto_appello"]["avvertenze"])
        assert "20 gg" in avv and "70 gg" not in avv

    def test_sfratto_nessuna_soglia_due_canoni(self):
        # art. 5 L. 392/1978: un canone non pagato dopo 20 giorni; le due mensilita' solo per gli oneri
        avv = " ".join(_CATALOGO["sfratto_morosita"]["avvertenze"])
        assert ">= 2 canoni" not in avv and "20 gg" in avv

    def test_gravi_g493_non_tornano(self):
        # G-493: the four entries no longer carry the claims that lost the act or the right
        for tipo in ("opposizione_decreto_ingiuntivo", "relata_pec_opposizione_di"):
            avv = " ".join(_CATALOGO[tipo]["avvertenze"])
            assert "40 giorni dalla notifica" not in avv and "fissato nel decreto" in avv, tipo
            assert "art. 641 c.p.c." in _CATALOGO[tipo]["riferimenti_normativi"], tipo
        assert "termine_fissato_nel_decreto" in _CATALOGO["opposizione_decreto_ingiuntivo"]["campi_obbligatori"]
        for tipo in ("opposizione_decreto_ingiuntivo", "relata_pec_opposizione_di"):
            assert "C. Cost. 120/1976" in " ".join(_CATALOGO[tipo]["avvertenze"]), tipo  # art. 650, nota (26)
        assert "art. 316 co. 1" in " ".join(_CATALOGO["opposizione_decreto_ingiuntivo"]["avvertenze"])
        # LI-086, option (b): art. 645 co. 3 is quoted as written, and the warning says that the
        # comma it refers to is shown as repealed on Normattiva. No other model quotes it.
        avv_645 = [a for a in _CATALOGO["opposizione_decreto_ingiuntivo"]["avvertenze"] if "art. 645 co. 3" in a]
        assert len(avv_645) == 1
        assert "l'anticipazione di cui all'art. 163-bis, secondo comma" in avv_645[0]
        assert avv_645[0].endswith("Su Normattiva l'art. 163-bis, secondo comma, c.p.c. risulta abrogato dal "
                                   "D.Lgs. 10 ottobre 2022, n. 149, come modificato dalla L. 29 dicembre 2022, "
                                   "n. 197")
        assert [t for t, e in _CATALOGO.items() if "163-bis, secondo comma" in " ".join(e.get("avvertenze", []))] \
            == ["opposizione_decreto_ingiuntivo"]
        avviso = _CATALOGO["avviso_543_5_cpc"]
        assert "debitore pignorato" not in avviso["descrizione"] and "terzo pignorato" in avviso["descrizione"]
        assert {"numero_ruolo", "data_udienza_comparizione"} <= set(avviso["campi_obbligatori"])
        assert "solo verso quelli non avvisati" not in " ".join(avviso["avvertenze"])
        vendita = _CATALOGO["vendita_immobili"]
        assert "stima" not in vendita["campi_opzionali"] and "calcolo_valore_catastale" not in vendita["tool_calcolo"]
        assert not any(a.lower().startswith("allegare relazione di stima") for a in vendita["avvertenze"])
        assert {"art. 497 c.p.c.", "art. 501 c.p.c."} <= set(vendita["riferimenti_normativi"])

    def test_precetto_avvertenze_e_calcoli_195(self):
        # #195: art. 644 c.p.c. is the decreto ingiuntivo's rule; the precetto's own are artt. 480 and 481
        # (read on Normattiva on 2026-11-22). Interest after the claim (art. 1284 co. 4 c.c.) and on partial
        # payments (art. 1194 c.c.) have their own tools; the fee is priced on the precetto's own table.
        e = _CATALOGO["atto_di_precetto"]
        avv = " ".join(e["avvertenze"])
        assert "644" not in avv
        assert "novanta giorni dalla sua notificazione" in avv and "art. 627" in avv
        assert "non minore di dieci giorni" in avv and "giudice competente per l'esecuzione" in avv
        assert {"interessi_legali", "interessi_corso_causa", "interessi_acconti", "modello_notula"} == set(e["tool_calcolo"])

    def test_art_644_solo_nei_decreti_ingiuntivi(self):
        for tipo, e in _CATALOGO.items():
            if "art. 644" in " ".join(e.get("avvertenze", [])):
                assert e["routing"].get("tool") == "decreto_ingiuntivo", tipo

    def test_monitorio_e_precetto_non_prezzati_con_le_fasi_di_cognizione(self):
        # #195: parcella_avvocato_civile prices the cognition phases; the monitorio (single phase)
        # and the precetto have their own D.M. 55/2014 tables, priced by modello_notula.
        for tipo in ("decreto_ingiuntivo_ordinario", "decreto_ingiuntivo_professionale", "atto_di_precetto"):
            e = _CATALOGO[tipo]
            assert "parcella_avvocato_civile" not in e["tool_calcolo"], tipo
            assert "modello_notula" in e["tool_calcolo"], tipo
            assert "modello_notula(tipo_procedimento=" in " ".join(e["avvertenze"]), tipo
            assert "totale_onorari" in " ".join(e["avvertenze"]), tipo  # the notula total holds the costs too

    def test_interessi_mora_data_di_scadenza(self):
        # #195: interessi_mora counts from the day after data_inizio (art. 4 co. 1 D.Lgs. 231/2002):
        # every model that feeds it says data_inizio is the due date.
        for tipo, e in _CATALOGO.items():
            if "interessi_mora" in e.get("tool_calcolo", []):
                assert "dal giorno successivo" in " ".join(e["avvertenze"]), tipo

    def test_sollecito_formale_mora_rivalutazione_solo_come_maggior_danno(self):
        # #195: on D.Lgs. 231/2002 interest the revaluation is the greater damage of art. 1224 co. 2 c.c.
        avv = " ".join(_CATALOGO["sollecito_formale_mora"]["avvertenze"])
        assert "art. 1224, co. 2, c.c." in avv and "non si sommano" in avv
        assert "convenuta la misura degli interessi moratori" in avv  # art. 1224 co. 2, second sentence

    def test_relata_penale_art_152_cpp(self):
        rif = _CATALOGO["relata_pec_penale"]["riferimenti_normativi"]
        assert "art. 152 c.p.p." in rif and "L. 53/1994" not in rif

    def test_parametri_fissi_solo_parametri_del_tool_e_variante_separata(self):
        r = genera_modello_atto("relata_pec_appello")
        assert r["parametri_fissi"] == {} and r["variante"] == {"tipo_relata": "appello"}

    def test_tipo_credito_dei_modelli_accettato_dal_tool(self):
        # #203: decreto_ingiuntivo_fatture routed to tipo_credito='fatture', which the tool refused.
        # Every decreto ingiuntivo model now passes a tipo_credito the tool accepts.
        from mcp_legal_it.tools.atti_giudiziari import decreto_ingiuntivo

        fn = getattr(decreto_ingiuntivo, "fn", decreto_ingiuntivo)
        for tipo, e in _CATALOGO.items():
            if e["routing"].get("tool") != "decreto_ingiuntivo":
                continue
            r = fn(creditore="A", debitore="B", importo=5000, **e["routing"]["parametri_fissi"])
            assert "errore" not in r, (tipo, r.get("errore"))
        assert _CATALOGO["decreto_ingiuntivo_fatture"]["routing"]["parametri_fissi"] == {"tipo_credito": "commerciale"}

    def test_decreto_ingiuntivo_ordinario_rinvia_al_modello_fatture(self):
        # #203: a commercial credit (D.Lgs. 231/2002) goes to the invoice model, with late-payment interest
        # from the day after the due date and no formal demand (art. 4 co. 1, read 2026-11-26)
        avv = " ".join(genera_modello_atto("decreto_ingiuntivo_ordinario")["avvertenze"])
        assert "decreto_ingiuntivo_fatture" in avv
        assert "senza che sia necessaria la costituzione in mora (art. 4 co. 1 D.Lgs. 231/2002)" in avv

    def test_precetto_avverte_che_interessi_acconti_applica_il_saggio_legale(self):
        # #202: interessi_acconti has no rate choice; the precetto model says so and names the tool
        # for the art. 1284 co. 4 rate
        avv = [a for a in _CATALOGO["atto_di_precetto"]["avvertenze"] if a.startswith("interessi_acconti")]
        assert len(avv) == 1
        assert "art. 1284 co. 1 c.c." in avv[0] and "art. 1284 co. 4 c.c." in avv[0]
        assert "interessi_corso_causa" in avv[0] and "non gestisce acconti" in avv[0]


# ---------------------------------------------------------------------------
# esporta_atto_docx — Markdown to Word, offline (the live gate repeats these)
# ---------------------------------------------------------------------------

import re as _re

import pytest as _pytest


@_pytest.fixture
def esporta(tmp_path, monkeypatch):
    from docx import Document

    from mcp_legal_it.tools import modelli_atti

    monkeypatch.setattr(modelli_atti, "_OUTPUT_DIR", str(tmp_path / "out"))
    fn = getattr(modelli_atti.esporta_atto_docx, "fn", modelli_atti.esporta_atto_docx)

    def run(testo, titolo="Atto"):
        out = fn(testo=testo, titolo=titolo)
        path = _re.search(r"File salvato: (.+\.docx)", out).group(1)
        return Document(path)
    return run


def _numeri(doc):
    """Numbers Word shows for 'List Number' paragraphs (counter per numId, from startOverride)."""
    from docx.oxml.ns import qn

    inizi = {}
    for num in doc.part.numbering_part.element.findall(qn("w:num")):
        start = num.find(f"./{qn('w:lvlOverride')}[@{qn('w:ilvl')}='0']/{qn('w:startOverride')}")
        if start is not None:
            inizi[num.get(qn("w:numId"))] = int(start.get(qn("w:val")))
    contatori, resi = {}, []
    for p in doc.paragraphs:
        if p.style.name != "List Number":
            continue
        num_id = p._p.pPr.find(f".//{qn('w:numId')}").get(qn("w:val"))
        contatori[num_id] = contatori.get(num_id, inizi.get(num_id, 1) - 1) + 1
        resi.append(contatori[num_id])
    return resi


def test_docx_liste_numerate_conservano_i_numeri(esporta):
    doc = esporta("1. primo\n2. secondo\n\nParagrafo\n\n1. nuova\n2. seconda\n\n10. decimo")
    assert _numeri(doc) == [1, 2, 1, 2, 10]


def test_docx_titoli_e_grassetto_corsivo_senza_asterischi(esporta):
    doc = esporta("## **Fatto** e *diritto*\nTesto con ***grassetto corsivo*** e resto")
    heading, par = doc.paragraphs[0], doc.paragraphs[1]
    assert heading.style.name == "Heading 2" and "*" not in heading.text
    assert "*" not in par.text
    runs = {r.text: (bool(r.bold), bool(r.italic)) for r in par.runs}
    assert runs["grassetto corsivo"] == (True, True)
    assert runs[" e resto"] == (False, False)


def test_docx_titolo_in_intestazione(esporta):
    doc = esporta("Corpo.", titolo="Parere pro veritate")
    assert "Parere pro veritate" in doc.sections[0].header.paragraphs[0].text

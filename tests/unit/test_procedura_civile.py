import importlib

import pytest


def _call(fn_name: str, **kwargs):
    mod = importlib.import_module("mcp_legal_it.tools.procedura_civile")
    fn = getattr(mod, fn_name)
    actual = fn.fn if hasattr(fn, "fn") else fn
    return actual(**kwargs)


# ---------------------------------------------------------------------------
# competenza_giudice
# ---------------------------------------------------------------------------

class TestCompetenzaGiudice:
    def test_valore_3000_civile_gdp(self):
        result = _call("competenza_giudice", valore_causa=3000.0)
        assert result["giudice_competente"] == "Giudice di Pace"
        assert "7" in result["articolo"]
        assert result["materia_riservata"] is False

    def test_valore_esatto_soglia_10000_gdp(self):
        # Soglia GdP beni mobili: €10.000 (art. 7 c.p.c., riforma Cartabia D.Lgs. 149/2022)
        result = _call("competenza_giudice", valore_causa=10_000.0)
        assert result["giudice_competente"] == "Giudice di Pace"

    def test_valore_oltre_10000_civile_tribunale(self):
        result = _call("competenza_giudice", valore_causa=10_001.0)
        assert result["giudice_competente"] == "Tribunale"
        assert "9" in result["articolo"]

    def test_circolazione_15000_gdp(self):
        result = _call("competenza_giudice", valore_causa=15_000.0, materia="circolazione_stradale")
        assert result["giudice_competente"] == "Giudice di Pace"
        assert "7" in result["articolo"]

    def test_circolazione_esatta_soglia_25000_gdp(self):
        # Soglia GdP circolazione: €25.000 (art. 7 c.p.c., riforma Cartabia D.Lgs. 149/2022)
        result = _call("competenza_giudice", valore_causa=25_000.0, materia="circolazione_stradale")
        assert result["giudice_competente"] == "Giudice di Pace"

    def test_circolazione_oltre_25000_tribunale(self):
        result = _call("competenza_giudice", valore_causa=25_001.0, materia="circolazione_stradale")
        assert result["giudice_competente"] == "Tribunale"

    def test_lavoro_tribunale_sezione_lavoro(self):
        result = _call("competenza_giudice", valore_causa=500.0, materia="lavoro")
        assert "Tribunale" in result["giudice_competente"]
        assert "Lavoro" in result["giudice_competente"] or "lavoro" in result["note"].lower()
        assert result["materia_riservata"] is True

    def test_locazione_tribunale_riservata(self):
        result = _call("competenza_giudice", valore_causa=1000.0, materia="locazione")
        assert result["giudice_competente"] == "Tribunale"
        assert result["materia_riservata"] is True

    def test_condominio_non_riservato_al_tribunale(self):
        # Art. 9 c.p.c. non menziona il condominio; art. 7 co. 1 (mobili fino a 10.000 euro)
        # e co. 3 n. 2 (cause in materia di condominio, qualunque valore): 500 euro -> GdP.
        result = _call("competenza_giudice", valore_causa=500.0, materia="condominio")
        assert result["giudice_competente"] == "Giudice di Pace"
        assert result["materia_riservata"] is False
        assert _call("competenza_giudice", valore_causa=20_000.0, materia="condominio")["giudice_competente"] == "Tribunale"

    def test_materie_esclusive_art_9_co_2_e_immobili_tribunale(self):
        # Art. 9 co. 2 c.p.c. (letto su Normattiva): querela di falso, imposte e tasse, esecuzione forzata.
        for m in ("querela_di_falso", "imposte_tasse", "esecuzione_forzata", "usucapione", "immobili"):
            assert _call("competenza_giudice", valore_causa=1_000.0, materia=m)["giudice_competente"] == "Tribunale", m

    def test_art_7_co_3_gdp_qualunque_valore(self):
        r = _call("competenza_giudice", valore_causa=500_000.0, materia="servitu")
        assert r["giudice_competente"] == "Giudice di Pace"

    def test_materia_non_riconosciuta_rifiutata(self):
        with pytest.raises(ValueError):
            _call("competenza_giudice", valore_causa=1_000.0, materia="astrologia")

    def test_crisi_impresa_tribunale_comi_art_27_ccii(self):
        r = _call("competenza_giudice", valore_causa=1.0, materia="crisi_impresa")
        assert "specializzata" not in r["giudice_competente"].lower()
        assert "27" in r["articolo"]

    def test_famiglia_tribunale_riservata(self):
        result = _call("competenza_giudice", valore_causa=0.0, materia="famiglia")
        assert result["giudice_competente"] == "Tribunale"
        assert result["materia_riservata"] is True

    def test_fallimento_tribunale_specializzata(self):
        result = _call("competenza_giudice", valore_causa=100_000.0, materia="fallimento")
        assert "Tribunale" in result["giudice_competente"]
        assert result["materia_riservata"] is True

    def test_crisi_impresa_tribunale_specializzata(self):
        result = _call("competenza_giudice", valore_causa=50_000.0, materia="crisi_impresa")
        assert "Tribunale" in result["giudice_competente"]
        assert result["materia_riservata"] is True

    def test_valore_negativo_errore(self):
        with pytest.raises(ValueError):
            _call("competenza_giudice", valore_causa=-100.0)

    def test_valore_zero_gdp(self):
        result = _call("competenza_giudice", valore_causa=0.0)
        assert result["giudice_competente"] == "Giudice di Pace"

    def test_campi_risposta_presenti(self):
        result = _call("competenza_giudice", valore_causa=3000.0)
        for campo in ("giudice_competente", "articolo", "valore_causa", "materia", "materia_riservata", "note", "soglia_gdp_euro"):
            assert campo in result


# ---------------------------------------------------------------------------
# verifica_mediazione_obbligatoria
# ---------------------------------------------------------------------------

class TestVerificaMediazione:
    def test_condominio_obbligatoria(self):
        result = _call("verifica_mediazione_obbligatoria", materia="condominio")
        assert result["obbligatoria"] is True
        assert result["materia_trovata"] == "condominio"
        assert "2010" in result["fonte"]

    def test_locazione_obbligatoria(self):
        result = _call("verifica_mediazione_obbligatoria", materia="locazione")
        assert result["obbligatoria"] is True

    def test_franchising_obbligatoria_cartabia(self):
        result = _call("verifica_mediazione_obbligatoria", materia="franchising")
        assert result["obbligatoria"] is True
        assert "Cartabia" in result["fonte"]

    def test_contratti_bancari_obbligatoria(self):
        result = _call("verifica_mediazione_obbligatoria", materia="contratti_bancari")
        assert result["obbligatoria"] is True

    def test_responsabilita_medica_obbligatoria(self):
        result = _call("verifica_mediazione_obbligatoria", materia="responsabilita_medica")
        assert result["obbligatoria"] is True

    def test_societa_di_persone_cartabia(self):
        result = _call("verifica_mediazione_obbligatoria", materia="societa_di_persone")
        assert result["obbligatoria"] is True
        assert "Cartabia" in result["fonte"]

    def test_lavoro_non_determinabile(self):
        # Not in the table is not «not listed»: never False for an unknown matter (#195).
        result = _call("verifica_mediazione_obbligatoria", materia="lavoro")
        assert result["obbligatoria"] is None
        assert result["materia_trovata"] is None

    def test_appalti_non_determinabile(self):
        result = _call("verifica_mediazione_obbligatoria", materia="appalti")
        assert result["obbligatoria"] is None

    def test_case_insensitive(self):
        result = _call("verifica_mediazione_obbligatoria", materia="CONDOMINIO")
        assert result["obbligatoria"] is True

    def test_spazi_normalizzati(self):
        result = _call("verifica_mediazione_obbligatoria", materia="patti di famiglia")
        assert result["obbligatoria"] is True

    def test_esclusioni_sempre_presenti(self):
        result = _call("verifica_mediazione_obbligatoria", materia="condominio")
        assert isinstance(result["esclusioni_applicabili"], list)
        assert len(result["esclusioni_applicabili"]) > 0

    def test_riferimento_normativo(self):
        result = _call("verifica_mediazione_obbligatoria", materia="locazione")
        assert "28/2010" in result["riferimento_normativo"]

    def test_rete_e_accenti_art_5_co_1(self):
        # Art. 5 co. 1 D.Lgs. 28/2010 elenca 'rete', 'responsabilita' medica e sanitaria',
        # 'societa' di persone' (letto su Normattiva): alias e accenti devono agganciarle.
        for m in ("rete", "contratto di rete", "responsabilità medica", "società di persone"):
            assert _call("verifica_mediazione_obbligatoria", materia=m)["obbligatoria"] is True, m

    def test_generico_o_vuoto_non_agganciano_una_voce(self):
        for m in ("contratti", "", "  "):
            r = _call("verifica_mediazione_obbligatoria", materia=m)
            assert r["obbligatoria"] is None and r["materia_trovata"] is None, m

    def test_esclusioni_art_5_co_6_otto_lettere(self):
        # Art. 5 co. 6 D.Lgs. 28/2010, lett. a)-h); i provvedimenti cautelari (co. 5) non sono esclusi.
        r = _call("verifica_mediazione_obbligatoria", materia="condominio")
        assert len(r["esclusioni_applicabili"]) == 8
        assert not any("cautelar" in e.lower() for e in r["esclusioni_applicabili"])
        assert "non preclude" in r["nota_provvedimenti_urgenti"]

    def test_materia_non_riconosciuta_non_determinabile(self):
        # #195: an unknown matter is «non determinabile» with a pointer to art. 5 co. 1, never False.
        result = _call("verifica_mediazione_obbligatoria", materia="diritto_sportivo")
        assert result["obbligatoria"] is None
        assert result["materia_trovata"] is None
        assert "non determinabile" in result["note"].lower()
        assert "art. 5 co. 1" in result["note"]

    def test_circolazione_stradale_resta_fuori_elenco(self):
        # A known matter outside the list keeps False: negoziazione assistita instead (art. 3 D.L. 132/2014).
        result = _call("verifica_mediazione_obbligatoria", materia="circolazione stradale")
        assert result["obbligatoria"] is False
        assert "132/2014" in result["note"]

    def test_apostrofi_articoli_e_preposizioni_non_contano(self):
        # #195: «contratti d'opera» answered False although art. 5 co. 1 lists «opera».
        for m in ("contratti d'opera", "contratto d'opera", "Contratti di opera", "contratti d’opera",
                  "contratti opera", "CONTRATTI D'OPERA", "l'affitto di azienda"):
            r = _call("verifica_mediazione_obbligatoria", materia=m)
            assert r["obbligatoria"] is True, m
        assert _call("verifica_mediazione_obbligatoria", materia="contratti d'opera")["materia_trovata"] == "contratti_opera"

    def test_chiavi_della_tabella_non_si_sovrappongono(self):
        # Dropping articles and prepositions must not make two matters share a key,
        # nor a composite item of art. 5 co. 1 shadow a single matter.
        from mcp_legal_it.tools.procedura_civile import _chiave_materia, _load_mediazione

        tabella = _load_mediazione()
        chiavi: dict[str, str] = {}
        for m in tabella["materie"]:
            for k in (m["nome"], *m.get("alias", [])):
                assert chiavi.setdefault(_chiave_materia(k), m["nome"]) == m["nome"], k
        nomi = {m["nome"] for m in tabella["materie"]}
        for voce in tabella["voci_composte"]:
            assert _chiave_materia(voce["voce"]) not in chiavi, voce["voce"]
            assert set(voce["materie"]) <= nomi and len(voce["materie"]) > 1, voce

    # Every item of art. 5 co. 1 D.Lgs. 28/2010 in force (read on Normattiva on 2026-11-22), in the
    # norm's own words. The «non determinabile» note quotes the same list: a user who copies an item
    # from it must get True, not null again.
    _VOCI_ART_5_CO_1 = (
        "condominio", "diritti reali", "divisione", "successioni ereditarie", "patti di famiglia",
        "locazione", "comodato", "affitto di aziende",
        "risarcimento del danno derivante da responsabilità medica e sanitaria",
        "risarcimento del danno derivante da responsabilità medica e sanitaria e da diffamazione con il "
        "mezzo della stampa o con altro mezzo di pubblicità",
        "diffamazione con il mezzo della stampa o con altro mezzo di pubblicità",
        "contratti assicurativi, bancari e finanziari", "associazione in partecipazione", "consorzio",
        "franchising", "opera", "rete", "somministrazione", "società di persone", "subfornitura",
    )

    def test_ogni_voce_dell_art_5_co_1_nelle_parole_della_norma_e_obbligatoria(self):
        nota = _call("verifica_mediazione_obbligatoria", materia="diritto_sportivo")["note"]
        for voce in self._VOCI_ART_5_CO_1:
            assert voce in nota, f"la nota «non determinabile» non riporta {voce!r}"
            r = _call("verifica_mediazione_obbligatoria", materia=voce)
            assert r["obbligatoria"] is True and r["materia_trovata"], (voce, r)
        # Spellings of the same items that a user writes by hand
        for voce in ("contratti assicurativi bancari e finanziari", "diffamazione con altro mezzo di pubblicità",
                     "diffamazione con il mezzo della stampa", "Contratti assicurativi, bancari e finanziari"):
            assert _call("verifica_mediazione_obbligatoria", materia=voce)["obbligatoria"] is True, voce

    def test_voce_composta_elenca_tutte_le_materie(self):
        r = _call("verifica_mediazione_obbligatoria", materia="contratti assicurativi, bancari e finanziari")
        assert r["materia_trovata"] == "contratti_assicurativi, contratti_bancari, contratti_finanziari"
        assert r["fonte"] == "originaria (2010)"

    def test_sinistro_stradale_resta_fuori_elenco(self):
        for m in ("sinistro stradale", "circolazione_stradale"):
            r = _call("verifica_mediazione_obbligatoria", materia=m)
            assert r["obbligatoria"] is False and "negoziazione assistita" in r["note"], m


# ---------------------------------------------------------------------------
# gratuito_patrocinio
# ---------------------------------------------------------------------------

class TestGratuitoPatrocinio:
    def test_reddito_basso_ammesso(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=10_000.0)
        assert result["ammesso"] is True
        assert result["margine"] > 0

    def test_reddito_alto_non_ammesso(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=20_000.0)
        assert result["ammesso"] is False
        assert result["margine"] < 0

    def test_reddito_esatto_soglia_ammesso(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=13_659.64)
        assert result["ammesso"] is True
        assert result["margine"] == pytest.approx(0.0, abs=0.01)

    def test_reddito_sopra_soglia_di_un_cent_non_ammesso(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=13_659.65)
        assert result["ammesso"] is False

    def test_penale_soglia_maggiorata_con_familiari(self):
        # 13659.64 + 2*1032.91 = 15725.46
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=15_000.0,
            n_familiari_conviventi=2,
            ambito="penale",
        )
        assert result["ammesso"] is True
        assert result["soglia_applicata"] == pytest.approx(15_725.46, abs=0.01)

    def test_penale_senza_familiari_soglia_base(self):
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=10_000.0,
            n_familiari_conviventi=0,
            ambito="penale",
        )
        assert result["soglia_applicata"] == pytest.approx(13_659.64, abs=0.01)

    def test_redditi_familiari_sommati(self):
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=5_000.0,
            redditi_familiari=[4_000.0, 3_000.0],
        )
        assert result["reddito_totale_nucleo"] == pytest.approx(12_000.0, abs=0.01)
        assert result["ammesso"] is True

    def test_redditi_familiari_sopra_soglia(self):
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=5_000.0,
            redditi_familiari=[5_000.0, 5_000.0],
        )
        assert result["reddito_totale_nucleo"] == pytest.approx(15_000.0, abs=0.01)
        assert result["ammesso"] is False

    def test_vittima_violenza_sempre_ammessa(self):
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=100_000.0,
            vittima_violenza=True,
        )
        assert result["ammesso"] is True
        assert result["vittima_violenza"] is True
        assert "automatica" in result["note"].lower()

    def test_vittima_violenza_reddito_zero(self):
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=0.0,
            vittima_violenza=True,
        )
        assert result["ammesso"] is True

    def test_interessi_in_conflitto_solo_reddito_personale(self):
        # Art. 76 co. 4 DPR 115/2002: only the applicant's own income counts when
        # the applicant's interests conflict with those of the cohabiting family.
        # 9000 <= 13659.64, margin 4659.64 (the household 39000 would exceed it).
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=9_000.0,
            n_familiari_conviventi=1,
            redditi_familiari=[30_000.0],
            interessi_in_conflitto=True,
        )
        assert result["ammesso"] is True
        assert result["reddito_totale_nucleo"] == pytest.approx(9_000.0, abs=0.01)
        assert result["margine"] == pytest.approx(4_659.64, abs=0.01)
        assert result["solo_reddito_personale"] is True

    def test_diritti_personalita_solo_reddito_personale(self):
        # Art. 76 co. 4 DPR 115/2002: same rule when the case concerns personality rights.
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=9_000.0,
            n_familiari_conviventi=1,
            redditi_familiari=[30_000.0],
            diritti_personalita=True,
        )
        assert result["ammesso"] is True
        assert result["margine"] == pytest.approx(4_659.64, abs=0.01)

    def test_senza_flag_reddito_nucleo_sommato(self):
        # Art. 76 co. 2: without the co. 4 flags the household income is summed.
        result = _call(
            "gratuito_patrocinio",
            reddito_richiedente=9_000.0,
            n_familiari_conviventi=1,
            redditi_familiari=[30_000.0],
        )
        assert result["ammesso"] is False
        assert result["margine"] == pytest.approx(-25_340.36, abs=0.01)

    def test_reddito_negativo_errore(self):
        with pytest.raises(ValueError):
            _call("gratuito_patrocinio", reddito_richiedente=-1.0)

    def test_riferimento_normativo_presente(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=10_000.0)
        assert "DPR 115/2002" in result["riferimento_normativo"]
        assert "13.659,64" in result["riferimento_normativo"]

    def test_campi_risposta_presenti(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=10_000.0)
        for campo in ("ammesso", "vittima_violenza", "reddito_richiedente", "reddito_totale_nucleo",
                      "soglia_applicata", "margine", "ambito", "note", "riferimento_normativo"):
            assert campo in result

    def test_ambito_default_civile(self):
        result = _call("gratuito_patrocinio", reddito_richiedente=10_000.0)
        assert result["ambito"] == "civile"

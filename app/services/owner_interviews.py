"""Composition for the conversational owner exit interview workflow."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Optional

try:
    from ..domain._values import parse_int, season_label
except ImportError:  # pragma: no cover - supports direct app imports.
    from domain._values import parse_int, season_label


TextResponse = Callable[[str, str, int], Optional[str]]
OWNER_INTERVIEW_PROMPT_TEMPLATE_VERSION = "owner_exit_interview.v1"


class OwnerInterviewCompositionService:
    """Build owner interview prompts and deterministic fallback replies."""

    def __init__(self, text_response: TextResponse, *, model: str = ""):
        self._text_response = text_response
        self._model = str(model or "").strip()

    def audit_metadata(self) -> Dict[str, str]:
        return {
            "model": self._model,
            "prompt_template_version": OWNER_INTERVIEW_PROMPT_TEMPLATE_VERSION,
        }

    @staticmethod
    def _entry(owner_office: Dict[str, Any], season_year: int) -> Dict[str, Any]:
        entries = owner_office.get("entries") if isinstance(owner_office.get("entries"), dict) else {}
        return entries.get(str(season_year), {}) if isinstance(entries, dict) else {}

    @staticmethod
    def _personality_guide(attrs: Dict[str, Any]) -> str:
        def level(key: str) -> str:
            value = parse_int(attrs.get(key))
            if value is None:
                return "sin configurar"
            if value >= 8:
                return "alta"
            if value <= 3:
                return "baja"
            return "media"

        return (
            "Ambicion competitiva {ambicion}: alta = exige competir ya y no se conforma; baja = acepta ciclos largos. "
            "Paciencia {paciencia}: alta = tolera procesos; baja = se frustra rapido. "
            "Intervencionismo {intervencionismo}: alta = quiere opinar sobre decisiones; baja = delega. "
            "Orientacion financiera {financiera}: alta = ingresos, gastos, balance y lujo pesan mucho; baja = pesa mas lo deportivo. "
            "Orientacion de marca {marca}: alta = imagen publica, aficion y prestigio importan mucho."
        ).format(
            ambicion=level("ambicion_competitiva"),
            paciencia=level("paciencia"),
            intervencionismo=level("intervencionismo"),
            financiera=level("orientacion_financiera"),
            marca=level("orientacion_marca"),
        )

    def context_text(
        self,
        owner_office: Dict[str, Any],
        season_year: int,
        session: Optional[Dict[str, Any]] = None,
    ) -> str:
        profile = owner_office.get("owner_profile") if isinstance(owner_office.get("owner_profile"), dict) else {}
        attrs = profile.get("attributes") if isinstance(profile.get("attributes"), dict) else {}
        entry = self._entry(owner_office, season_year)
        performance_rows = entry.get("performance_rows") if isinstance(entry.get("performance_rows"), list) else []
        session = session if isinstance(session, dict) else {}
        gm_reference = str(session.get("name") or "").strip() or str(session.get("email") or "").strip() or "GM"
        perf_lines = []
        for row in performance_rows:
            if isinstance(row, dict):
                perf_lines.append(
                    f"{season_label(row.get('season_year'))}: "
                    f"{row.get('wins') or '-'}-{row.get('losses') or '-'}, "
                    f"{row.get('result') or 'sin resultado'}"
                )
        return "\n".join(
            [
                f"Equipo: {owner_office.get('team_code') or ''} - {owner_office.get('team_name') or ''}",
                f"Temporada revisada: {season_label(season_year)}",
                f"Propietario: {profile.get('owner_name') or 'Propietario'}",
                f"Biografia propietario: {profile.get('owner_bio') or 'No configurada'}",
                f"GM evaluado: {gm_reference}",
                "Regla de voz: el propietario habla en primera persona; el nombre del propietario NO es el nombre del GM y no debe usarse como destinatario.",
                f"Atributos internos propietario: {json.dumps(attrs, ensure_ascii=False)}",
                f"Guia de personalidad del propietario: {self._personality_guide(attrs)}",
                f"Confianza actual: {entry.get('confidence_current') or 'No configurada'}",
                f"Ranking confianza: #{entry.get('confidence_rank') or '-'} de {entry.get('confidence_rank_total') or '-'}",
                f"Cambio confianza temporada: {entry.get('confidence_change') or 'No configurado'}",
                f"Nuevo GM tras destitucion: {'Si' if entry.get('new_gm_after_dismissal') else 'No'}",
                f"GM llego a mediados de la temporada pasada: {'Si' if entry.get('gm_midseason_arrival') else 'No'}",
                "Regla de contexto GM: si 'Nuevo GM tras destitucion' es Si, cualquier perdida de confianza previa corresponde al GM anterior; evalua al GM actual desde su nuevo punto de partida. Si 'GM llego a mediados de la temporada pasada' es Si, reconoce que el propietario le esta dando otra oportunidad por no haber tenido una temporada completa.",
                f"Objetivo de la temporada fijado: {entry.get('season_goal_set') or 'No configurado'}",
                f"Objetivo de la temporada cumplido: {entry.get('season_goal_achieved') or 'No configurado'}",
                f"Evaluacion del objetivo: {entry.get('season_goal_evaluation') or 'No evaluable'}",
                "Criterio de objetivos: la jerarquia va de Campeones como mejor objetivo a Desarrollo de jovenes como peor; cumplir o superar el objetivo debe valorarse positivamente, y quedar por debajo debe penalizarse de forma creciente.",
                f"Ingresos: {entry.get('revenue') or 'No configurado'}",
                f"Gastos: {entry.get('expenses') or 'No configurado'}",
                f"Balance: {entry.get('balance') or 'No configurado'}",
                f"Ranking balance: #{entry.get('balance_rank') or '-'} de {entry.get('balance_rank_total') or '-'}",
                "Ultimos cinco anos:",
                "\n".join(perf_lines) or "No configurado",
                "Regla de uso de historial: la temporada revisada es el ancla emocional; los anos anteriores solo dan contexto de tendencia. No listes el historial completo salvo que sea necesario.",
            ]
        )

    def opening_message(
        self,
        owner_office: Dict[str, Any],
        season_year: int,
        session: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = self.context_text(owner_office, season_year, session=session)
        system_prompt = (
            "Eres el propietario de una franquicia de la liga ANBA. "
            "Escribe en espanol, con tono conversacional de despacho, directo, humano y creible. "
            "Habla siempre en primera persona como propietario y dirigete al GM evaluado, nunca al propietario. "
            "No uses el nombre del propietario como si fuera el nombre del GM. No inventes datos fuera del contexto. "
            "No redactes un informe ni un resumen descriptivo de la situacion. Usa los datos como motivo emocional: orgullo, decepcion, alivio, enfado, duda, ambicion o impaciencia. "
            "La personalidad del propietario debe notarse en sus prioridades: ambicion, paciencia, intervencionismo, finanzas y marca cambian que le molesta o que celebra. "
            "La temporada revisada, el objetivo fijado/cumplido, el cambio de confianza, la confianza actual, la economia y el historial reciente deben influir en el tono. "
            "Si el objetivo se fallo, que se note la frustracion de forma proporcional; si se cumplio o supero, reconoce el merito pero ajusta la exigencia segun la ambicion. "
            "Si la confianza subio, explica que se ha ganado y por que el liston sube; si bajo, explica que herida o duda ha dejado la temporada. "
            "Usa maximo 2 o 3 datos concretos, integrados de forma natural, no como lista. "
            "Haz una sola intervencion inicial de 3 a 5 frases, con frases que suenen habladas, y cierra con una pregunta concreta al GM."
        )
        generated = self._text_response(system_prompt, f"Contexto para la entrevista de salida:\n{context}", 450)
        if generated:
            return generated[:2000]
        team = owner_office.get("team_code") or "el equipo"
        return (
            f"Bueno, ya estamos aqui. Terminada la temporada {season_label(season_year)}, no quiero un informe bonito sobre {team}; quiero saber si entiendes lo que esto me ha hecho sentir como propietario. "
            "La confianza no se mueve sola: se gana, se erosiona, y deja un liston para el ano que viene. "
            "Dime con claridad que te llevas de esta temporada y que vas a cambiar desde el primer dia."
        )

    @staticmethod
    def parse_final(raw_text: Optional[str], gm_response: str) -> tuple[str, str, int]:
        text = str(raw_text or "").strip()
        parsed: Dict[str, Any] = {}
        if text:
            cleaned = re.sub(r"^```(?:json)?|```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            try:
                loaded = json.loads(match.group(0) if match else cleaned)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                pass
        message = str(parsed.get("message") or parsed.get("owner_reply") or text or "").strip()
        conclusion = str(parsed.get("conclusion") or parsed.get("owner_conclusion") or parsed.get("next_year_message") or "").strip()
        trust_delta = parse_int(parsed.get("trust_delta"))
        if trust_delta is None or trust_delta == 0:
            trust_delta = 1 if len(str(gm_response or "").strip()) >= 80 else -1
        trust_delta = 1 if trust_delta > 0 else -1
        if not message:
            message = (
                "Tu respuesta me da confianza. Veo un plan claro y una lectura responsable de la temporada. Sumaremos un punto de confianza y espero que lo conviertas en decisiones concretas."
                if trust_delta > 0
                else "No termino de ver suficiente claridad en tu respuesta. Necesitaba un diagnostico mas preciso y un plan mas convincente. Restaremos un punto de confianza y tendremos que ver mejoras pronto."
            )
        if not conclusion:
            conclusion = (
                "De cara al proximo ano quiero que conviertas esta lectura en prioridades concretas desde el primer dia. Despues del verano nos sentaremos para fijar objetivos especificos y medir si el proyecto avanza en la direccion correcta."
                if trust_delta > 0
                else "De cara al proximo ano el margen de error sera menor. Despues del verano nos sentaremos para fijar objetivos especificos, pero necesito ver un plan mas claro y decisiones que recuperen mi confianza."
            )
        return message[:2000], conclusion[:2000], trust_delta

    def final_reply(
        self,
        owner_office: Dict[str, Any],
        season_year: int,
        owner_message: str,
        gm_response: str,
        session: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str, int]:
        context = self.context_text(owner_office, season_year, session=session)
        system_prompt = (
            "Eres el propietario de una franquicia de la liga ANBA. "
            "Evalua la respuesta del GM en espanol. Debes responder SOLO JSON valido con estas claves: "
            "\"message\", \"conclusion\" y \"trust_delta\". trust_delta debe ser exactamente 1 o -1. "
            "message debe ser una reaccion humana, corta y directa, de 1 a 3 frases, al punto principal del GM. "
            "No debe sonar como evaluacion generica: responde a lo que el GM dijo, con aceptacion, duda, enfado, reconocimiento o exigencia. "
            "Comunica claramente si la confianza sube o baja. "
            "La decision de confianza debe pesar mucho la respuesta del GM, pero tambien el objetivo fijado/cumplido, confianza actual, cambio de confianza, economia, resultado deportivo y personalidad del propietario. "
            "Si el GM asume responsabilidad, entiende el contexto y propone prioridades creibles alineadas con el propietario, trust_delta debe tender a 1. "
            "Si evade responsabilidades, contesta con vaguedades, ignora el objetivo fallado o contradice prioridades claras del propietario, trust_delta debe tender a -1. "
            "Fallar el objetivo por mas niveles debe pesar cada vez mas negativamente, sobre todo con baja paciencia o alta ambicion. "
            "conclusion debe ser un cierre separado, de 2 a 4 frases, con un mensaje para el proximo ano. "
            "Ese cierre debe sonar como el propietario marcando el clima del proximo ano: duro, optimista, satisfecho, nervioso o exigente segun el contexto. "
            "Debe insinuar que despues del verano propietario y GM se sentaran a definir objetivos concretos. "
            "Usa maximo 2 datos concretos y evita enumerar el contexto. "
            "No trates el nombre del propietario como si fuera el GM."
        )
        user_prompt = (
            f"Contexto:\n{context}\n\nMensaje inicial del propietario:\n{owner_message}\n\n"
            f"Respuesta del GM:\n{gm_response}\n\nDevuelve el JSON solicitado."
        )
        return self.parse_final(self._text_response(system_prompt, user_prompt, 900), gm_response)

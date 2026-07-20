"""Pure prompt composition for generated league-news imagery."""

from __future__ import annotations

from typing import List, Mapping, Optional


TEAM_IMAGE_COLORS = {
    "ATL": "#E03A3E, #C1D32F",
    "BKN": "#000000, #FFFFFF",
    "BOS": "#007A33, #BA9653",
    "CHA": "#1D1160, #00788C",
    "CHI": "#CE1141, #000000",
    "CLE": "#860038, #FDBB30",
    "DAL": "#00538C, #002F5F",
    "DEN": "#0E2240, #FEC524",
    "DET": "#C8102E, #1D42BA",
    "GSW": "#1D428A, #FFC72C",
    "HOU": "#CE1141, #000000",
    "IND": "#002D62, #FDBB30",
    "LAC": "#C8102E, #1D428A",
    "LAL": "#552583, #FDB927",
    "MEM": "#12173F, #5D76A9",
    "MIA": "#98002E, #000000",
    "MIL": "#00471B, #EEE1C6",
    "MIN": "#0C2340, #9EA2A2",
    "NOP": "#0C2340, #C8102E",
    "NYK": "#006BB6, #F58426",
    "OKC": "#007AC1, #EF3B24",
    "ORL": "#0077C0, #000000",
    "PHI": "#006BB6, #ED174C",
    "PHX": "#E56020, #1D1160",
    "POR": "#E03A3E, #000000",
    "SAC": "#5A2D81, #63727A",
    "SAS": "#000000, #C4CED4",
    "TOR": "#CE1141, #000000",
    "UTA": "#002B5C, #00471B",
    "WAS": "#002B5C, #E31837",
}


class NewsImagePromptService:
    DEFAULT_COLORS = "#0F766E, #111827"

    def __init__(self, palette: Optional[Mapping[str, str]] = None) -> None:
        self.palette = dict(palette or TEAM_IMAGE_COLORS)

    def colors_for(self, team_code: str) -> str:
        return self.palette.get(str(team_code or "").upper(), self.DEFAULT_COLORS)

    def build(
        self,
        headline: str,
        description: str,
        *,
        teams: Optional[List[str]] = None,
        players: Optional[List[str]] = None,
        context: Optional[str] = None,
        team_name: Optional[str] = None,
        team_code: Optional[str] = None,
        player_name: Optional[str] = None,
        secondary_headline: Optional[str] = None,
        additional_details: Optional[str] = None,
        transaction_type: Optional[str] = None,
        use_player_reference: bool = False,
    ) -> str:
        if use_player_reference:
            return self._reference_prompt(
                headline,
                description,
                teams=teams,
                players=players,
                context=context,
                team_name=team_name,
                team_code=team_code,
                player_name=player_name,
                secondary_headline=secondary_headline,
                additional_details=additional_details,
                transaction_type=transaction_type,
            )
        return self._generic_prompt(headline, description, teams=teams, players=players, context=context)

    def _reference_prompt(
        self,
        headline: str,
        description: str,
        *,
        teams: Optional[List[str]],
        players: Optional[List[str]],
        context: Optional[str],
        team_name: Optional[str],
        team_code: Optional[str],
        player_name: Optional[str],
        secondary_headline: Optional[str],
        additional_details: Optional[str],
        transaction_type: Optional[str],
    ) -> str:
        resolved_team_code = str(team_code or (teams or [""])[0] or "").upper()
        resolved_team_name = str(team_name or resolved_team_code or "ANBA").strip()
        resolved_player_name = str(player_name or (players or [""])[0] or "Jugador").strip()
        return f"""Create a professional NBA social media breaking news graphic using the uploaded player image as the primary reference.

IMPORTANT PLAYER REFERENCE INSTRUCTIONS

- Use the uploaded photo as the source reference.
- Preserve the player's facial features, hair, skin tone, expression, body proportions, and overall likeness accurately.
- The player must remain clearly recognizable as the same person from the reference image.
- Do not alter age, ethnicity, facial structure, hairstyle, or physical characteristics.
- Remove the original team uniform and replace it with an authentic, realistic {resolved_team_name} uniform.
- Jersey colors, typography, trim, logos, and styling should accurately reflect the team's current branding.
- Maintain realistic jersey fabric, lighting, wrinkles, and athletic appearance.
- The player should appear as if photographed professionally while playing for {resolved_team_name}.

DESIGN OBJECTIVE

Create a premium NBA transaction announcement graphic suitable for major basketball news accounts on Twitter/X, Instagram, Threads, and sports media websites.

VISUAL STYLE

- Professional NBA media graphic
- Bleacher Report quality
- ESPN social media quality
- House of Highlights quality
- Courtside Buzz style presentation
- Modern sports marketing creative
- Premium Photoshop compositing
- Editorial sports poster
- High-end sports journalism graphic
- Viral social media design
- Clean information hierarchy
- Photorealistic athlete rendering
- Ultra-sharp details
- Dynamic contrast
- Dramatic lighting
- Premium typography

LAYOUT

- Landscape format (16:9)
- Player positioned on the right side occupying approximately 50-60% of the composition
- Large headline typography on the left side
- Team logo integrated into the background at low opacity
- Team branding incorporated throughout the design
- Strong focal point on the player
- Clean visual hierarchy optimized for mobile viewing
- Professional spacing and alignment

BACKGROUND

- Dark textured sports background
- Arena atmosphere
- Subtle smoke and lighting effects
- Team color gradients
- Depth and cinematic lighting
- Modern sports poster aesthetic

TEAM BRANDING

Team:
{resolved_team_name}

Primary Colors:
{self.colors_for(resolved_team_code)}

Use the team's visual identity consistently throughout:
- Color palette
- Logo integration
- Background treatments
- Typography accents
- Graphic elements

HEADLINE TEXT

NBA NEWS

{resolved_team_name}

{headline}

SUBHEADLINE

{secondary_headline or description}

PLAYER NAME

{resolved_player_name}

OPTIONAL DETAILS

{additional_details or context or ""}

TRANSACTION CONTEXT

Transaction Type:
{transaction_type or "Transaction"}

Examples:
- Trade
- Signing
- Re-signing
- Contract Extension
- Waived
- Released
- Team Option Exercised
- Team Option Declined
- Qualifying Offer Rejected
- Two-Way Signing
- Conversion to Standard Contract
- Buyout
- Draft Rights Acquired
- Contract Guaranteed
- Contract Non-Guaranteed
- Free Agency Signing

QUALITY REQUIREMENTS

- Photorealistic
- Sports media publication quality
- Crisp typography
- Authentic NBA branding aesthetic
- Realistic jersey replacement
- No distorted anatomy
- No cartoon appearance
- No AI-art look
- Premium Photoshop-style finish
- Suitable for posting directly by an NBA news account
- Highly shareable social media design"""

    @staticmethod
    def _generic_prompt(
        headline: str,
        description: str,
        *,
        teams: Optional[List[str]],
        players: Optional[List[str]],
        context: Optional[str],
    ) -> str:
        team_text = ", ".join(str(team).upper() for team in teams or [] if str(team or "").strip()) or "ANBA"
        player_text = ", ".join(str(player) for player in players or [] if str(player or "").strip())
        parts = [
            "Create a landscape professional basketball news graphic for a Discord/social post.",
            "Use an editorial transaction-news style with dramatic arena lighting, premium sports typography, and team-color accents.",
            f"Main headline text exactly: {headline}",
            f"Post context: {description}",
            f"Relevant team(s): {team_text}.",
            "Avoid official league marks, sponsor logos, watermarks, and unrelated extra text.",
            "Do not include a fake scoreboard or stat table. Leave enough clean space around the headline for mobile readability.",
        ]
        if player_text:
            parts.append(
                f"Relevant player name(s): {player_text}. If showing a player, use a generic basketball player in team-inspired colors."
            )
        if context:
            parts.append(f"Additional context: {context}")
        return "\n".join(parts)

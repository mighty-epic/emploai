"""Skill command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


def build_skill_command_handlers(
    *,
    security_manager,
    rate_limited,
    get_session,
    track_command_usage,
    safe_reply,
):
    @rate_limited(security_manager)
    async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List available skills and their status."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "skills")

        if not session.skill_registry:
            await safe_reply(update, "❌ Skill system not initialized.")
            return

        available_skills = session.skill_registry.gating.list_available_skills()
        unavailable = session.skill_registry.gating._unavailable_skills

        if not available_skills and not unavailable:
            await safe_reply(
                update,
                "**📚 Skills**\n\n"
                "No skills loaded. Skills should be in the `skills/` directory.\n\n"
                "Use the skill-creator skill to make new skills!",
            )
            return

        lines = ["**📚 Available Skills**\n"]

        for skill in available_skills:
            invocable = "👤" if skill.metadata.user_invocable else ""
            lines.append(f"• **{skill.name}** {invocable}\n  {skill.description[:80]}...")

        if unavailable:
            lines.append("\n**🔒 Gated Skills** (need setup)\n")
            for name, reason in unavailable.items():
                lines.append(f"• {name}: {reason}")

        lines.append("\n\nSkills load automatically based on your messages.")
        lines.append("Use `/skill <name>` to invoke a specific skill.")

        await safe_reply(update, "\n".join(lines))

    @rate_limited(security_manager)
    async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Invoke a specific skill manually."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "skill")

        if not context.args:
            await safe_reply(
                update,
                "**Usage:** /skill <skill-name>\n\n"
                "Manually invoke a specific skill.\n"
                "Example: `/skill skill-creator`",
            )
            return

        skill_name = context.args[0]
        skill = session.skill_registry.loader.get_skill(skill_name)

        if not skill:
            await safe_reply(update, f"❌ Skill not found: `{skill_name}`")
            return

        if not session.skill_registry.gating.is_available(skill_name):
            reason = session.skill_registry.gating.get_unavailable_reason(skill_name)
            await safe_reply(update, f"🔒 Skill not available: {reason}")
            return

        session.active_skills = [skill_name]

        await safe_reply(
            update,
            "**📖 Skill: "
            f"{skill.name}**\n\n"
            f"{skill.description}\n\n"
            "Context loaded. This skill will now be active for your next messages.",
        )

    @rate_limited(security_manager)
    async def skilltest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Validate a skill and show diagnostics."""
        user = update.effective_user
        session = get_session(user.id)
        track_command_usage(session, "skilltest")

        if not context.args:
            await safe_reply(update, "**Usage:** /skilltest <skill-name>")
            return

        skill_name = context.args[0]
        if not session.skill_registry:
            await safe_reply(update, "❌ Skill system not initialized.")
            return

        result = session.skill_registry.validate_skill(skill_name)
        if not result.get("valid"):
            lines = [f"❌ **Skill Validation Failed:** `{skill_name}`\n"]
            for err in result.get("errors", []):
                lines.append(f"• {err}")
            for warn in result.get("warnings", []):
                lines.append(f"⚠️ {warn}")
            await safe_reply(update, "\n".join(lines))
            return

        resources = result.get("resources", {})
        lines = [f"✅ **Skill Valid:** `{skill_name}`\n"]
        if result.get("warnings"):
            lines.append("**Warnings:**")
            for warn in result["warnings"]:
                lines.append(f"• {warn}")
        lines.append("\n**Resources:**")
        lines.append(f"• Scripts: {len(resources.get('scripts', []))}")
        lines.append(f"• References: {len(resources.get('references', []))}")
        lines.append(f"• Assets: {len(resources.get('assets', []))}")
        await safe_reply(update, "\n".join(lines))

    return {
        "skills_command": skills_command,
        "skill_command": skill_command,
        "skilltest_command": skilltest_command,
    }

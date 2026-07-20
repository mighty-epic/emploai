"""
Skill System for Telegram Agent
Modular capability system inspired by AgentSkills/moltbot
"""

import os
import re
import yaml
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime

from shared.subprocess_utils import hidden_subprocess_kwargs


logger = logging.getLogger(__name__)


def resolve_default_skills_dir() -> Path:
    """Resolve the skill directory for local-first standalone runs."""
    bundled_dir = Path(__file__).parent.parent / "skills"
    configured = os.getenv("EMPLOAI_SKILLS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    runtime_home = os.getenv("EMPLOAI_HOME", "").strip()
    if not runtime_home:
        return bundled_dir

    user_dir = Path(runtime_home).expanduser().resolve() / "skills"
    try:
        from shared.local_skill_sync import sync_bundled_skills

        sync_bundled_skills(bundled_dir, user_dir)
    except Exception:
        logger.debug("Failed to sync bundled skills into local runtime home", exc_info=True)
    return user_dir


@dataclass
class SkillMetadata:
    """Skill metadata from YAML frontmatter."""
    name: str
    description: str
    homepage: Optional[str] = None
    metadata_json: Optional[Dict] = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    command_dispatch: Optional[str] = None
    command_tool: Optional[str] = None
    command_arg_mode: str = "raw"


@dataclass
class SkillResource:
    """A skill resource (script, reference, or asset)."""
    path: Path
    resource_type: str  # "script", "reference", "asset"
    name: str
    content: Optional[str] = None
    loaded: bool = False


@dataclass
class Skill:
    """A loaded skill with progressive disclosure support."""
    metadata: SkillMetadata
    skill_path: Path
    body: str = ""  # SKILL.md body content
    body_loaded: bool = False
    resources: Dict[str, SkillResource] = field(default_factory=dict)
    loaded_at: datetime = field(default_factory=datetime.now)
    
    @property
    def name(self) -> str:
        return self.metadata.name
    
    @property
    def description(self) -> str:
        return self.metadata.description


class SkillLoader:
    """
    Loads and manages skills from the skills directory.
    
    Skills are loaded progressively:
    1. Metadata (name + description) - Always loaded, small (~100 words)
    2. Body - Loaded when skill triggers (up to 5k words)
    3. Resources - Loaded as needed (unlimited, scripts executable without loading)
    """
    
    def __init__(self, skills_dir: Optional[Path] = None):
        """
        Initialize skill loader.
        
        Args:
            skills_dir: Directory containing skill folders. Defaults to ./skills
        """
        if skills_dir is None:
            skills_dir = resolve_default_skills_dir()
        
        self.skills_dir = Path(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self._load_skills()
    
    def _load_skills(self):
        """Load all skills from the skills directory."""
        self.skills.clear()
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return
        
        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir():
                skill_md = skill_path / "SKILL.md"
                if skill_md.exists():
                    try:
                        skill = self._parse_skill(skill_path)
                        if skill:
                            self.skills[skill.name] = skill
                            logger.info(f"Loaded skill: {skill.name}")
                    except Exception as e:
                        logger.error(f"Failed to load skill from {skill_path}: {e}")
        
        logger.info(f"Loaded {len(self.skills)} skills from {self.skills_dir}")

    def reload(self) -> None:
        """Reload skill metadata from disk."""
        self._load_skills()
    
    def _parse_skill(self, skill_path: Path) -> Optional[Skill]:
        """
        Parse a skill from its directory.
        
        Only loads metadata initially - body and resources loaded on demand.
        """
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return None
        
        content = skill_md.read_text(encoding='utf-8')
        
        # Parse YAML frontmatter
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if not frontmatter_match:
            logger.warning(f"No frontmatter found in {skill_md}")
            return None
        
        try:
            frontmatter = yaml.safe_load(frontmatter_match.group(1))
            body = frontmatter_match.group(2)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML frontmatter in {skill_md}: {e}")
            return None
        
        # Extract metadata
        metadata = SkillMetadata(
            name=frontmatter.get('name', skill_path.name),
            description=frontmatter.get('description', ''),
            homepage=frontmatter.get('homepage'),
            metadata_json=frontmatter.get('metadata'),
            user_invocable=frontmatter.get('user-invocable', True),
            disable_model_invocation=frontmatter.get('disable-model-invocation', False),
            command_dispatch=frontmatter.get('command-dispatch'),
            command_tool=frontmatter.get('command-tool'),
            command_arg_mode=frontmatter.get('command-arg-mode', 'raw')
        )
        
        skill = Skill(
            metadata=metadata,
            skill_path=skill_path,
            body="",
            body_loaded=False
        )
        
        # Scan for resources but don't load them yet
        self._scan_resources(skill)
        
        return skill

    def _load_skill_body(self, skill: Skill) -> None:
        """Load SKILL.md body on demand."""
        if skill.body_loaded:
            return
        skill_md = skill.skill_path / "SKILL.md"
        content = skill_md.read_text(encoding='utf-8')
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        skill.body = frontmatter_match.group(2) if frontmatter_match else content
        skill.body_loaded = True
    
    def _scan_resources(self, skill: Skill):
        """Scan skill directory for resources without loading them."""
        # Scripts
        scripts_dir = skill.skill_path / "scripts"
        if scripts_dir.exists():
            for script in scripts_dir.iterdir():
                if script.is_file():
                    skill.resources[script.name] = SkillResource(
                        path=script,
                        resource_type="script",
                        name=script.name
                    )
        
        # References
        references_dir = skill.skill_path / "references"
        if references_dir.exists():
            for ref in references_dir.iterdir():
                if ref.is_file():
                    skill.resources[ref.name] = SkillResource(
                        path=ref,
                        resource_type="reference",
                        name=ref.name
                    )
        
        # Assets
        assets_dir = skill.skill_path / "assets"
        if assets_dir.exists():
            for asset in assets_dir.iterdir():
                skill.resources[asset.name] = SkillResource(
                    path=asset,
                    resource_type="asset",
                    name=asset.name
                )
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self.skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """List all loaded skills."""
        return list(self.skills.values())
    
    def search_skills(self, query: str) -> List[Skill]:
        """Search skills by name or description."""
        query_lower = query.lower()
        return [
            skill for skill in self.skills.values()
            if query_lower in skill.name.lower() 
            or query_lower in skill.description.lower()
        ]
    
    def load_resource(self, skill_name: str, resource_name: str) -> Optional[SkillResource]:
        """Load a specific resource from a skill."""
        skill = self.skills.get(skill_name)
        if not skill:
            return None
        if include_body:
            self._load_skill_body(skill)
        
        resource = skill.resources.get(resource_name)
        if not resource:
            return None
        
        if not resource.loaded:
            try:
                resource.content = resource.path.read_text(encoding='utf-8')
                resource.loaded = True
            except Exception as e:
                logger.error(f"Failed to load resource {resource_name}: {e}")
                return None
        
        return resource
    
    def execute_script(self, skill_name: str, script_name: str, 
                       args: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute a script from a skill.
        
        Scripts can be run without loading into context, making them token-efficient
        and deterministic for fragile operations.
        """
        skill = self.skills.get(skill_name)
        if not skill:
            return {"error": f"Skill not found: {skill_name}"}
        
        resource = skill.resources.get(script_name)
        if not resource or resource.resource_type != "script":
            return {"error": f"Script not found: {script_name}"}
        
        script_path = resource.path
        
        # Determine interpreter based on file extension
        if script_path.suffix == '.py':
            cmd = ['python3', str(script_path)]
        elif script_path.suffix == '.sh':
            cmd = ['bash', str(script_path)]
        elif script_path.suffix == '.js':
            cmd = ['node', str(script_path)]
        else:
            cmd = [str(script_path)]
        
        if args:
            cmd.extend(args)
        
        try:
            import subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(skill.skill_path),
                **hidden_subprocess_kwargs(),
            )
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"error": f"Failed to execute script: {e}"}
    
    def get_skill_context(self, skill_name: str, include_body: bool = True,
                         include_resources: Optional[List[str]] = None) -> Optional[str]:
        """
        Get the full context for a skill including body and optionally resources.
        
        This is used when a skill is triggered to provide all relevant context
        to the LLM.
        """
        skill = self.skills.get(skill_name)
        if not skill:
            return None
        
        context_parts = [
            f"# {skill.name}",
            f"**Description:** {skill.description}",
            ""
        ]
        
        if include_body and skill.body:
            context_parts.append(skill.body)
        
        if include_resources:
            for resource_name in include_resources:
                resource = self.load_resource(skill_name, resource_name)
                if resource and resource.content:
                    context_parts.append(f"\n## {resource_name}\n")
                    context_parts.append(resource.content)
        
        return "\n".join(context_parts)

    def get_skill_detail(
        self,
        skill_name: str,
        *,
        include_body: bool = True,
        include_resources: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Return a progressive-disclosure detail view for a skill."""
        skill = self.skills.get(skill_name)
        if not skill:
            return None
        if include_body:
            self._load_skill_body(skill)

        resources = []
        for resource in skill.resources.values():
            item: Dict[str, Any] = {
                "name": resource.name,
                "type": resource.resource_type,
                "loaded": resource.loaded,
            }
            if include_resources and resource.resource_type == "reference":
                loaded = self.load_resource(skill_name, resource.name)
                if loaded and loaded.content is not None:
                    item["content"] = loaded.content
                    item["loaded"] = True
            resources.append(item)

        return {
            "name": skill.name,
            "description": skill.description,
            "path": str(skill.skill_path),
            "body": skill.body if include_body else "",
            "body_loaded": skill.body_loaded,
            "resources": sorted(resources, key=lambda item: (item["type"], item["name"])),
            "metadata": {
                "homepage": skill.metadata.homepage,
                "user_invocable": skill.metadata.user_invocable,
                "disable_model_invocation": skill.metadata.disable_model_invocation,
                "command_dispatch": skill.metadata.command_dispatch,
                "command_tool": skill.metadata.command_tool,
                "command_arg_mode": skill.metadata.command_arg_mode,
                "metadata": skill.metadata.metadata_json or {},
            },
        }


class SkillGating:
    """
    Manages skill gating based on environment, configuration, and binary availability.
    
    Skills can be gated by:
    - Environment variables (requires specific env vars to be set)
    - Configuration values (requires specific config settings)
    - Binary availability (requires specific binaries to be installed)
    """
    
    def __init__(self, skill_loader: SkillLoader):
        self.skill_loader = skill_loader
        self._available_skills: Set[str] = set()
        self._unavailable_skills: Dict[str, str] = {}  # skill_name -> reason
        self._check_gates()
    
    def _check_gates(self):
        """Check which skills are available based on their gates."""
        for skill in self.skill_loader.list_skills():
            reason = self._check_skill_gate(skill)
            if reason:
                self._unavailable_skills[skill.name] = reason
                logger.info(f"Skill gated: {skill.name} - {reason}")
            else:
                self._available_skills.add(skill.name)
    
    def _check_skill_gate(self, skill: Skill) -> Optional[str]:
        """
        Check if a skill is gated. Returns reason if gated, None if available.
        """
        if not skill.metadata.metadata_json:
            return None
        
        openclaw_meta = skill.metadata.metadata_json.get('openclaw', {})
        requires = openclaw_meta.get('requires', {})
        
        # Check environment variables
        env_vars = requires.get('env', [])
        for env_var in env_vars:
            if not os.getenv(env_var):
                return f"Requires environment variable: {env_var}"
        
        # Check binaries
        binaries = requires.get('bins', [])
        for binary in binaries:
            if not self._check_binary(binary):
                return f"Requires binary: {binary}"
        
        # Check config (would need config manager integration)
        # config_keys = requires.get('config', [])
        
        return None
    
    def _check_binary(self, binary: str) -> bool:
        """Check if a binary is available in PATH."""
        try:
            import subprocess
            subprocess.run(
                ['where.exe' if os.name == 'nt' else 'which', binary],
                capture_output=True,
                check=True,
                **hidden_subprocess_kwargs(),
            )
            return True
        except:
            return False
    
    def is_available(self, skill_name: str) -> bool:
        """Check if a skill is available (not gated)."""
        return skill_name in self._available_skills
    
    def get_unavailable_reason(self, skill_name: str) -> Optional[str]:
        """Get the reason a skill is unavailable."""
        return self._unavailable_skills.get(skill_name)
    
    def list_available_skills(self) -> List[Skill]:
        """List all available (non-gated) skills."""
        skills: List[Skill] = []
        for name in self._available_skills:
            skill = self.skill_loader.get_skill(name)
            if skill is not None:
                skills.append(skill)
        return skills
    
    def refresh(self):
        """Refresh gate checks (useful after environment changes)."""
        self._available_skills.clear()
        self._unavailable_skills.clear()
        self._check_gates()


class SkillRegistry:
    """
    Central registry for skills with triggering and execution support.
    
    This is the main interface for the Telegram agent to interact with skills.
    """
    
    def __init__(self, skills_dir: Optional[Path] = None):
        self.loader = SkillLoader(skills_dir)
        self.gating = SkillGating(self.loader)
        self._trigger_patterns: Dict[str, Callable[[str], bool]] = {}
        self._register_default_triggers()

    def reload(self) -> None:
        """Reload skills and gate state from disk."""
        self.loader.reload()
        self.gating.refresh()
        self._trigger_patterns.clear()
        self._register_default_triggers()
    
    def _register_default_triggers(self):
        """Register default trigger patterns for skills."""
        for skill in self.gating.list_available_skills():
            # Create a simple trigger based on skill name and description keywords
            keywords = self._extract_keywords(skill.description)
            
            def make_trigger(kws):
                return lambda text: any(kw in text.lower() for kw in kws)
            
            self._trigger_patterns[skill.name] = make_trigger(keywords)
    
    def _extract_keywords(self, description: str) -> List[str]:
        """Extract trigger keywords from a description."""
        # Simple keyword extraction - could be more sophisticated
        words = description.lower().split()
        # Filter for meaningful words (length > 3, not common words)
        common = {'with', 'from', 'this', 'that', 'when', 'where', 'what', 'how', 'and', 'for', 'the', 'use'}
        return [w.strip('.,!?()[]{}') for w in words if len(w) > 3 and w not in common][:10]
    
    def find_triggered_skills(self, message: str) -> List[Skill]:
        """Find skills that should be triggered by a message."""
        triggered = []
        for skill in self.gating.list_available_skills():
            if skill.metadata.disable_model_invocation:
                continue
            
            # Check description-based trigger
            if self._trigger_patterns.get(skill.name, lambda x: False)(message):
                triggered.append(skill)
                continue
            
            # Check if skill name is mentioned
            if skill.name.replace('-', ' ') in message.lower():
                triggered.append(skill)
        
        return triggered
    
    def get_skills_index(self) -> str:
        """Get a concise index of all available skills and their descriptions."""
        available = self.gating.list_available_skills()
        if not available:
            return "No specialized skills currently available."
        
        index_parts = ["# AVAILABLE SPECIALIZED SKILLS", "You can pull the following skills into your context using the 'pull_skill' tool for better task performance:"]
        for skill in available:
            index_parts.append(f"- **{skill.name}**: {skill.description}")
        
        return "\n".join(index_parts)

    def get_skill_context_for_message(self, message: str) -> str:
        """
        Get combined context from all triggered skills.
        
        This is the main method to call before sending a message to the LLM.
        It returns the relevant skill instructions that should be prepended to
        the system prompt.
        """
        triggered = self.find_triggered_skills(message)
        
        if not triggered:
            return ""
        
        contexts = []
        for skill in triggered:
            context = self.loader.get_skill_context(skill.name)
            if context:
                contexts.append(context)
        
        return "\n\n---\n\n".join(contexts)

    def get_active_skills_context(self, skill_names: List[str]) -> str:
        """Get full combined context for explicitly loaded skills."""
        if not skill_names:
            return ""
            
        contexts = []
        for name in skill_names:
            context = self.loader.get_skill_context(name)
            if context:
                contexts.append(f"## ACTIVE SKILL: {name}\n\n{context}")
                
        return "\n\n---\n\n".join(contexts)

    def get_skill_detail(
        self,
        skill_name: str,
        *,
        include_body: bool = True,
        include_resources: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Return a detail view without changing active skills."""
        return self.loader.get_skill_detail(
            skill_name,
            include_body=include_body,
            include_resources=include_resources,
        )
    
    def get_user_invocable_skills(self) -> List[Skill]:
        """Get skills that can be invoked by users via slash commands."""
        return [
            skill for skill in self.gating.list_available_skills()
            if skill.metadata.user_invocable
        ]
    
    def execute_skill_command(self, skill_name: str, command: str, 
                             args: str = "") -> Dict[str, Any]:
        """
        Execute a skill command.
        
        For skills with command_dispatch="tool", this bypasses the model
        and executes directly.
        """
        skill = self.loader.get_skill(skill_name)
        if not skill:
            return {"error": f"Skill not found: {skill_name}"}
        
        if not self.gating.is_available(skill_name):
            reason = self.gating.get_unavailable_reason(skill_name)
            return {"error": f"Skill not available: {reason}"}
        
        # Check if skill supports direct dispatch
        if skill.metadata.command_dispatch == "tool":
            tool_name = skill.metadata.command_tool
            if tool_name:
                # Execute the tool directly
                return {"tool": tool_name, "command": command, "args": args}
        
        # Otherwise, return context for the model to handle
        context = self.loader.get_skill_context(skill_name)
        return {"context": context, "command": command, "args": args}

    def validate_skill(self, skill_name: str) -> Dict[str, Any]:
        """
        Validate a skill's structure and metadata.

        Returns a dict with validation results.
        """
        errors: List[str] = []
        warnings: List[str] = []

        skill = self.loader.get_skill(skill_name)
        if not skill:
            return {
                "valid": False,
                "errors": [f"Skill not found: {skill_name}"],
                "warnings": []
            }

        # Required metadata
        if not skill.metadata.name:
            errors.append("Missing required field: name")
        if not skill.metadata.description:
            errors.append("Missing required field: description")

        # Command dispatch validation
        if skill.metadata.command_dispatch == "tool" and not skill.metadata.command_tool:
            errors.append("command-dispatch is 'tool' but command-tool is missing")

        # Resource checks
        scripts = [r for r in skill.resources.values() if r.resource_type == "script"]
        references = [r for r in skill.resources.values() if r.resource_type == "reference"]
        assets = [r for r in skill.resources.values() if r.resource_type == "asset"]

        self.loader._load_skill_body(skill)
        if not skill.body.strip():
            warnings.append("SKILL.md body is empty")

        if scripts:
            for script in scripts:
                if not script.path.exists():
                    errors.append(f"Script missing: {script.name}")
                elif script.path.suffix not in {".py", ".sh", ".js", ".ts"}:
                    warnings.append(f"Unrecognized script type: {script.name}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "resources": {
                "scripts": [s.name for s in scripts],
                "references": [r.name for r in references],
                "assets": [a.name for a in assets]
            }
        }


# Global registry instance
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry(skills_dir: Optional[Path] = None) -> SkillRegistry:
    """Get or create the global skill registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry(skills_dir)
    return _global_registry

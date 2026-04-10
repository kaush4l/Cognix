from typing import Literal, List

from pydantic import BaseModel, Field, ValidationError
from pydantic.fields import PydanticUndefined
import json


def _split_respecting_parens(text: str) -> list[str]:
    """Split on commas, but only at depth 0 (outside nested parens/quotes)."""
    items = []
    depth = 0
    current = []
    in_str = None
    for ch in text:
        if in_str:
            current.append(ch)
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            current.append(ch)
            in_str = ch
        elif ch in ('(', '[', '{'):
            current.append(ch)
            depth += 1
        elif ch in (')', ']', '}'):
            current.append(ch)
            depth -= 1
        elif ch == ',' and depth == 0:
            items.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        items.append(''.join(current).strip())
    return [i for i in items if i]


class BaseResponse(BaseModel):
    response_type: Literal['json', 'toon'] = 'json'

    def get_instructions(self):
        parts = []
        skip_fields = {'response_type'}
        for name, info in type(self).model_fields.items():
            if name in skip_fields:
                continue
            # info is a Pydantic FieldInfo-like object (v2). Try to get
            # the annotation/type and a human-friendly type name.
            annotation = getattr(info, 'annotation', None)
            if annotation is None:
                annotation = getattr(info, 'type_', None)

            if hasattr(annotation, '__name__'):
                type_name = annotation.__name__
            else:
                # Fallback to string form for complex annotations
                type_name = str(annotation)

            # Prefer explicit description, otherwise show default or 'required'
            description = getattr(info, 'description', None)
            default = getattr(info, 'default', PydanticUndefined)
            required = getattr(info, 'required', False)

            if description:
                desc = description
            else:
                # Treat PydanticUndefined, Ellipsis and None as missing/default-required
                if required or default in (PydanticUndefined, ...) or default is None:
                    desc = 'required'
                else:
                    desc = repr(default)

            parts.append(f"'{name}': {type_name} = {desc}")
        # Delegate to format-specific helpers so JSON/TOON formatting is
        # separated and easier to manage.
        if self.response_type == 'json':
            return self._format_json(parts)
        return self._format_toon(parts)

    def _format_json(self, parts: list[str]) -> str:
        """Return the full instruction string for JSON responses."""
        body = '{\n' + ',\n'.join(parts) + '\n}'
        additional = (
            "Additional rules:\n"
            "- The response MUST be valid JSON.\n"
            "- The top-level object MUST contain exactly the fields listed above (no extra keys).\n"
            "- Arrays (lists) must be JSON arrays.\n"
        )
        return (
            "## RESPONSE FORMAT\n"
            "You MUST respond with EXACTLY the following fields and format:\n\n"
            f"{body}\n\n"
            f"{additional}"
        )

    def _format_toon(self, parts: list[str]) -> str:
        """Return the full instruction string for TOON responses.

        TOON output uses one field per line. List fields use parentheses with
        comma-separated items, and scalar fields use plain key=value syntax.
        """
        toon_lines = []
        for p in parts:
            name_type, _, desc = p.partition(' = ')
            name = name_type.split("':")[0].strip(" '")
            if 'List' in name_type:
                toon_lines.append(f"{name}=(item1,item2)")
            else:
                toon_lines.append(f"{name}=value")

        toon_body = '\n'.join(toon_lines)
        additional = (
            "Additional rules:\n"
            "- The response MUST follow the TOON compact format: one field per line, key=value.\n"
            "- Lists MUST be encoded as parentheses with comma-separated items, e.g. field=(a,b).\n"
            "- Values may be quoted with double quotes if they contain commas or parentheses.\n"
            "- Keys MUST match exactly the field names above and there must be no extra keys.\n"
        )
        return (
            "## RESPONSE FORMAT\n"
            "You MUST respond with EXACTLY the following fields and format:\n\n"
            f"{toon_body}\n\n"
            f"{additional}"
        )

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _parse_toon(self, text: str) -> dict:
        data = {}
        try:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            for line in lines:
                if '=' in line:
                    key, val = line.split('=', 1)
                elif ':' in line:
                    key, val = line.split(':', 1)
                else:
                    continue
                key = key.strip()
                val = val.strip()
                if val.startswith('(') and val.endswith(')'):
                    inner = val[1:-1].strip()
                    if inner == '':
                        data[key] = []
                    else:
                        data[key] = _split_respecting_parens(inner)
                else:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        data[key] = val[1:-1]
                    else:
                        data[key] = val
        except Exception:
            return {}
        return data

    def to_object(self, text: str):
        # Parse input according to response_type using the format-specific
        # parsers, then validate into a model instance. Never raise — return
        # a model instance (or None as last resort).
        model_cls = type(self)
        if self.response_type == 'json':
            data = self._parse_json(text)
        elif self.response_type == 'toon':
            data = self._parse_toon(text)
        else:
            data = {}

        # Filter data to known model fields only
        allowed = set(type(self).model_fields.keys())
        filtered = {k: v for k, v in data.items() if k in allowed}
        if 'action' in data and 'tool_call' not in filtered:
            filtered['tool_call'] = data['action']

        # Attempt validation/construction
        try:
            if hasattr(model_cls, 'model_validate'):
                return model_cls.model_validate(filtered)
            return model_cls(**filtered)
        except ValidationError:
            # Try light coercion and retry
            coerced = {}
            for name, info in type(self).model_fields.items():
                if name not in filtered:
                    continue
                val = filtered[name]
                annotation = getattr(info, 'annotation', None) or getattr(info, 'type_', None)
                try:
                    origin = getattr(annotation, '__origin__', None)
                    if origin is list or (isinstance(origin, type) and origin is list):
                        # Ensure value is a list
                        if not isinstance(val, list):
                            coerced[name] = [val]
                        else:
                            coerced[name] = val
                    else:
                        # Prefer string for non-list simple types
                        if isinstance(val, (list, dict)):
                            coerced[name] = val
                        else:
                            coerced[name] = str(val)
                except Exception:
                    coerced[name] = val

            try:
                if hasattr(model_cls, 'model_validate'):
                    return model_cls.model_validate(coerced)
                return model_cls(**coerced)
            except Exception:
                # Last resort: return an empty/default instance or None
                try:
                    return model_cls()
                except Exception:
                    return None


class ReActResponse(BaseResponse):
    observation: List[str] = Field(
        default_factory=list,
        description=(
            "Observation for the current step: a concise statement of what was observed "
            "from the environment, tools, or previous actions. Each entry should describe a "
            "single observable fact or event."
        )
    )
    thinking: List[str] = Field(
        default_factory=list,
        description=(
            "Thinking: elaborate on the observations, reason about them, and propose the next "
            "step(s) of the plan. This should be more detailed than observations and can include "
            "hypotheses and intermediate reasoning."
        )
    )
    tool_call: List[str] = Field(
        default_factory=list,
        description=(
            "Tool call (optional): reserve this block only when a tool needs to be performed. "
            "Use it only for the tool name and its parameters. If no tool is needed, leave this "
            "block empty."
        )
    )
    answer: str = Field(
        '',
        description=(
            "Answer: the final user-facing response. If no tool_call is specified, this field is returned "
            "directly to the user. It should be concise and complete."
        )
    )

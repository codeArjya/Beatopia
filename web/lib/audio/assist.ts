import type { AssistRequest, AssistResponse, ChatMessage, EditorState } from "../types/api";
import schema from "../../../shared/schema/api.schema.json";

// Validate the generated wire schema's assist subset without a new dependency.
// Replay remains authoritative for sequential clip references and resource limits.
interface WireSchema {
  $ref?: string;
  type?: string;
  const?: unknown;
  enum?: unknown[];
  anyOf?: WireSchema[];
  oneOf?: WireSchema[];
  properties?: Record<string, WireSchema>;
  required?: string[];
  items?: WireSchema;
  minimum?: number;
  maximum?: number;
}
const definitions: Record<string, WireSchema> = schema.$defs;
function matches(value: unknown, rule: WireSchema): boolean {
  if (rule.$ref) return matches(value, definitions[rule.$ref.replace("#/$defs/", "")]);
  if (rule.anyOf) return rule.anyOf.some((child) => matches(value, child));
  if (rule.oneOf) return rule.oneOf.filter((child) => matches(value, child)).length === 1;
  if ("const" in rule && value !== rule.const) return false;
  if (rule.enum && !rule.enum.includes(value)) return false;
  switch (rule.type) {
    case "null": return value === null;
    case "string": return typeof value === "string";
    case "boolean": return typeof value === "boolean";
    case "number": case "integer":
      return typeof value === "number" && Number.isFinite(value)
        && (rule.type !== "integer" || Number.isInteger(value))
        && (rule.minimum === undefined || value >= rule.minimum)
        && (rule.maximum === undefined || value <= rule.maximum);
    case "array": return Array.isArray(value) && !!rule.items && value.every((item) => matches(item, rule.items!));
    case "object": {
      if (!value || typeof value !== "object" || Array.isArray(value)) return false;
      const record = value as Record<string, unknown>;
      const properties = rule.properties ?? {};
      // Reject unknown fields so UI/runtime data cannot enter the wire payload.
      return (rule.required ?? []).every((key) => key in record)
        && Object.keys(record).every((key) => key in properties && matches(record[key], properties[key]));
    }
    default: return false;
  }
}

export function assistUnavailable(editor: EditorState | null): string | null {
  if (!editor) return "Load audio before asking for an edit.";
  if (editor.clips.some((clip) => clip.source.track_id === "local" || /^(blob|data):/i.test(clip.source.audio_url))) {
    return "Assist is unavailable for local audio. Manual editing and export are available.";
  }
  return null;
}

export function assistRequest(messages: ChatMessage[], editor: EditorState): AssistRequest {
  const unavailable = assistUnavailable(editor);
  if (unavailable) throw new Error(unavailable);
  const request: AssistRequest = { messages: structuredClone(messages), editor: structuredClone(editor) };
  if (!matches(request, definitions.AssistRequest)) throw new Error("The editor cannot be sent as a valid AssistRequest.");
  return request;
}

export function assistResponse(value: unknown): AssistResponse {
  if (!matches(value, definitions.AssistResponse)) throw new Error("Assist returned an invalid operation batch. No edits were applied.");
  return structuredClone(value) as AssistResponse;
}

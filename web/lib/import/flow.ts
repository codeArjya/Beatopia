// Pure rules for the import page (T7.1/T7.2): user-facing error text for upload failures.
import { ApiError } from "@/lib/api/client";

/** Message for a failed POST /imports. The server's own message is shown for format errors (it's specific). */
export function importErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "upload_too_large":
        return "That file is over the 25 MB limit.";
      case "unsupported_format":
        return `The server couldn't read that file: ${e.message}.`;
      case "bad_request":
        return `The upload was rejected: ${e.message}.`;
      case "timeout":
        return "The upload took too long. Check your connection and try again.";
      case "network_error":
        return "Couldn't reach the server. Check your connection and try again.";
      default:
        return e.message ? `Import failed: ${e.message}.` : "Import failed. Try again.";
    }
  }
  return "Import failed. Try again.";
}

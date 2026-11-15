import type { ComponentProps } from "react";

import { Input } from "@/components/ui/input";

/** App text input. Feature code uses this, never components/ui/input. */
export function AppInput(props: ComponentProps<typeof Input>) {
  return <Input {...props} />;
}

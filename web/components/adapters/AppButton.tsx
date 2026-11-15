import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";

/** App button. Feature code uses this, never components/ui/button, so the design pass restyles one place. */
export function AppButton(props: ComponentProps<typeof Button>) {
  return <Button {...props} />;
}

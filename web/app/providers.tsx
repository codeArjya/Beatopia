"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PreviewProvider } from "@/lib/preview/PreviewProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <PreviewProvider>
          {children}
          <Toaster theme="dark" />
        </PreviewProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

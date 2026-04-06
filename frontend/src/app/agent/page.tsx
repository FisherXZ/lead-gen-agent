"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import ChatInterface from "@/components/chat/ChatInterface";

function AgentPageContent() {
  const searchParams = useSearchParams();
  const context = searchParams.get("context") || undefined;
  return <ChatInterface initialContext={context} />;
}

export default function AgentPage() {
  return (
    <Suspense>
      <AgentPageContent />
    </Suspense>
  );
}

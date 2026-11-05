import { Check, Copy, Download, Image as ImageIcon, Mail, Send } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// mailto bodies past ~1800 characters get cut off by some mail apps, so long reports point to Copy or Download.
const MAILTO_LIMIT = 1800;

export function DeveloperDialog({ runId, className }: { runId: number; className?: string }) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = (open: boolean) => {
    if (!open || markdown) return;
    api.devSummary(runId).then((r) => setMarkdown(r.markdown)).catch((e: Error) => setError(e.message));
  };

  const copy = async () => {
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Your browser blocked copying. Use Download instead.");
    }
  };

  const download = () => {
    if (!markdown) return;
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `ghostshopper-report-${runId}.md` });
    a.click();
    URL.revokeObjectURL(url);
  };

  const body = markdown
    ? markdown.length > MAILTO_LIMIT
      ? `${markdown.slice(0, MAILTO_LIMIT)}\n\n(The full report is longer. Ask me to send the downloaded file.)`
      : markdown
    : "";
  const mailto = `mailto:?subject=${encodeURIComponent("Fixes for our online store (GhostShopper report)")}&body=${encodeURIComponent(body)}`;

  return (
    <Dialog onOpenChange={load}>
      <DialogTrigger asChild>
        <Button variant="outline" className={cn("h-10 border-line", className)}>
          <Send aria-hidden />
          Send to my developer
        </Button>
      </DialogTrigger>
      <DialogContent className="gap-5 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-lg tracking-[-0.01em]">Send to my developer</DialogTitle>
          <DialogDescription>
            The technical details your developer or web agency needs. Copy it, download it, or email it.
          </DialogDescription>
        </DialogHeader>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        <pre className="max-h-80 overflow-auto border bg-panel p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap">
          {markdown ?? "Loading the report…"}
        </pre>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button className="h-10" onClick={copy} disabled={!markdown}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button variant="outline" className="h-10 border-line" onClick={download} disabled={!markdown}>
            <Download aria-hidden />
            Download
          </Button>
          <Button variant="outline" className="h-10 border-line" asChild disabled={!markdown}>
            <a href={markdown ? mailto : undefined} className="no-underline">
              <Mail aria-hidden />
              Email
            </a>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ShowMeDialog({ src, title }: { src: string; title: string }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="inline-flex min-h-11 items-center gap-2 text-sm font-medium underline decoration-line underline-offset-4 hover:decoration-foreground"
        >
          <ImageIcon className="size-4" aria-hidden />
          Show me what the shopper saw
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="text-lg tracking-[-0.01em]">{title}</DialogTitle>
          <DialogDescription>What the AI shopper saw on your store.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[70vh] overflow-auto border">
          <img src={src} alt={`Screenshot: ${title}`} className="w-full" />
        </div>
      </DialogContent>
    </Dialog>
  );
}

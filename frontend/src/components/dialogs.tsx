import { Check, Copy, Download, Image as ImageIcon, Mail, Send } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { api } from "@/lib/api";

// mailto bodies past ~1800 characters get cut off by some mail apps, so long reports point to Copy or Download.
const MAILTO_LIMIT = 1800;

export function DeveloperDialog({ runId }: { runId: number }) {
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
        <Button variant="outline" className="h-12 w-full text-base sm:w-auto">
          <Send aria-hidden />
          Send to my developer
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Send to my developer</DialogTitle>
          <DialogDescription>
            This report has the technical details your developer or web agency needs. Copy it, download it, or email it.
          </DialogDescription>
        </DialogHeader>
        {error && <p className="text-sm text-bad" role="alert">{error}</p>}
        <pre className="max-h-80 overflow-auto rounded-lg border bg-muted/50 p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap">
          {markdown ?? "Loading the report…"}
        </pre>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button className="h-11" onClick={copy} disabled={!markdown}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button variant="outline" className="h-11" onClick={download} disabled={!markdown}>
            <Download aria-hidden />
            Download
          </Button>
          <Button variant="outline" className="h-11" asChild disabled={!markdown}>
            <a href={markdown ? mailto : undefined}>
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
        <Button variant="outline" className="h-11">
          <ImageIcon aria-hidden />
          Show me
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>What the AI shopper saw on your store.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[70vh] overflow-auto rounded-lg border">
          <img src={src} alt={`Screenshot: ${title}`} className="w-full" />
        </div>
      </DialogContent>
    </Dialog>
  );
}

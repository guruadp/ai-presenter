import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  Database,
  FileText,
  Plus,
  Tag,
  Trash2,
  Upload,
} from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  KBDocument,
  KBFact,
  KBLimitation,
  ago,
  kbApi,
} from "../api/kbs";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Input from "../components/ui/Input";
import Modal from "../components/ui/Modal";
import Spinner from "../components/ui/Spinner";
import Textarea from "../components/ui/Textarea";

type Tab = "documents" | "facts" | "limitations";

export default function KBDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("documents");

  const { data: kb, isLoading: kbLoading } = useQuery({
    queryKey: ["kbs", id],
    queryFn: () => kbApi.get(id!),
    enabled: !!id,
  });

  function invalidateKB() {
    queryClient.invalidateQueries({ queryKey: ["kbs", id] });
    queryClient.invalidateQueries({ queryKey: ["kbs"] });
  }

  if (kbLoading) {
    return (
      <div className="flex justify-center pt-20">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!kb) {
    return (
      <div className="flex flex-col items-center pt-20 gap-3">
        <AlertCircle size={32} className="text-red-400" />
        <p className="text-gray-500 text-sm">Knowledge base not found.</p>
        <Button variant="secondary" onClick={() => navigate("/kbs")}>
          Back to Knowledge Bases
        </Button>
      </div>
    );
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "documents", label: "Documents" },
    { key: "facts", label: "Structured Facts" },
    { key: "limitations", label: "Limitations" },
  ];

  return (
    <>
      {/* Breadcrumb + header */}
      <div className="mb-6">
        <button
          onClick={() => navigate("/kbs")}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-700 mb-4 transition-colors"
        >
          <ArrowLeft size={14} />
          Knowledge Bases
        </button>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center shrink-0">
            <Database size={20} className="text-indigo-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-gray-900">{kb.name}</h1>
              <Badge variant="indigo">v{kb.version}</Badge>
            </div>
            <p className="text-sm text-gray-400">
              by {kb.owner} · updated {ago(kb.updated_at)}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-6 gap-1">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
              activeTab === key
                ? "text-indigo-700"
                : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {label}
            {activeTab === key && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "documents" && (
        <DocumentsTab kbId={id!} onMutate={invalidateKB} />
      )}
      {activeTab === "facts" && (
        <FactsTab kbId={id!} onMutate={invalidateKB} />
      )}
      {activeTab === "limitations" && (
        <LimitationsTab kbId={id!} onMutate={invalidateKB} />
      )}
    </>
  );
}

/* ── Documents tab ─────────────────────────────────────────────────────────── */

function DocumentsTab({ kbId, onMutate }: { kbId: string; onMutate: () => void }) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [tags, setTags] = useState("");

  const { data: docs, isLoading } = useQuery({
    queryKey: ["kbs", kbId, "docs"],
    queryFn: () => kbApi.listDocuments(kbId),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, tags }: { file: File; tags: string }) =>
      kbApi.uploadDocument(
        kbId,
        file,
        tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs", kbId, "docs"] });
      onMutate();
      setPendingFile(null);
      setTags("");
    },
  });

  function handleFile(file: File) {
    setPendingFile(file);
    setTags("");
  }

  return (
    <>
      {/* Drop zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-8 text-center mb-6 cursor-pointer transition-colors ${
          dragOver
            ? "border-indigo-400 bg-indigo-50"
            : "border-gray-200 hover:border-indigo-300 hover:bg-gray-50"
        }`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files[0];
          if (f) handleFile(f);
        }}
      >
        <Upload
          size={24}
          className={`mx-auto mb-2 ${dragOver ? "text-indigo-500" : "text-gray-300"}`}
        />
        <p className="text-sm text-gray-600">
          Drop a file here, or{" "}
          <span className="text-indigo-600 font-medium">browse</span>
        </p>
        <p className="text-xs text-gray-400 mt-1">.pdf · .docx · .txt · .md</p>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx,.txt,.md"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
          e.target.value = "";
        }}
      />

      {/* Document list */}
      {isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : !docs?.length ? (
        <EmptyState
          icon={<FileText size={40} />}
          title="No documents yet"
          description="Upload a PDF, DOCX, TXT or Markdown file to add it to this knowledge base."
        />
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  File
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Tags
                </th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Chunks
                </th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Ingested
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {docs.map((doc) => (
                <DocRow key={doc.id} doc={doc} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Upload modal */}
      {pendingFile && (
        <Modal
          title="Upload Document"
          onClose={() => setPendingFile(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setPendingFile(null)}>
                Cancel
              </Button>
              <Button
                loading={uploadMutation.isPending}
                icon={<Upload size={14} />}
                onClick={() =>
                  uploadMutation.mutate({ file: pendingFile, tags })
                }
              >
                Upload
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3 bg-gray-50 rounded-lg px-3 py-2.5">
              <FileText size={16} className="text-gray-400 shrink-0" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">
                  {pendingFile.name}
                </p>
                <p className="text-xs text-gray-400">
                  {(pendingFile.size / 1024).toFixed(1)} KB
                </p>
              </div>
            </div>
            <Input
              label="Tags"
              placeholder="product, pricing, docs"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              hint="Comma-separated — used to scope retrieval"
            />
            {uploadMutation.error && (
              <p className="text-xs text-red-500">
                {(uploadMutation.error as Error).message}
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function DocRow({ doc }: { doc: KBDocument }) {
  return (
    <tr className="hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-gray-300 shrink-0" />
          <span className="font-medium text-gray-800">{doc.filename}</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1 flex-wrap">
          {doc.tags.length ? (
            doc.tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-md"
              >
                <Tag size={9} />
                {t}
              </span>
            ))
          ) : (
            <span className="text-xs text-gray-300">—</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <Badge variant="green">{doc.chunk_count}</Badge>
      </td>
      <td className="px-4 py-3 text-right text-xs text-gray-400">
        {ago(doc.ingested_at)}
      </td>
    </tr>
  );
}

/* ── Facts tab ─────────────────────────────────────────────────────────────── */

function FactsTab({ kbId, onMutate }: { kbId: string; onMutate: () => void }) {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ key: "", value: "", source: "" });

  const { data: facts, isLoading } = useQuery({
    queryKey: ["kbs", kbId, "facts"],
    queryFn: () => kbApi.listFacts(kbId),
  });

  const addMutation = useMutation({
    mutationFn: () =>
      kbApi.addFact(kbId, {
        key: form.key,
        value: form.value,
        source: form.source || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs", kbId, "facts"] });
      onMutate();
      setShowAdd(false);
      setForm({ key: "", value: "", source: "" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (factId: string) => kbApi.deleteFact(kbId, factId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs", kbId, "facts"] });
      onMutate();
    },
  });

  return (
    <>
      <div className="flex justify-end mb-4">
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus size={13} />}
          onClick={() => setShowAdd(true)}
        >
          Add Fact
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : !facts?.length ? (
        <EmptyState
          icon={<Database size={40} />}
          title="No structured facts yet"
          description="Add key-value facts (price, specs, limits) that will always be answered exactly — never generated."
          action={
            <Button
              size="sm"
              icon={<Plus size={13} />}
              onClick={() => setShowAdd(true)}
            >
              Add First Fact
            </Button>
          }
        />
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide w-40">
                  Key
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Value
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Source
                </th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {facts.map((fact) => (
                <FactRow
                  key={fact.id}
                  fact={fact}
                  onDelete={() => deleteMutation.mutate(fact.id)}
                  deleting={deleteMutation.isPending}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <Modal
          title="Add Structured Fact"
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setShowAdd(false)}>
                Cancel
              </Button>
              <Button
                loading={addMutation.isPending}
                disabled={!form.key.trim() || !form.value.trim()}
                onClick={() => addMutation.mutate()}
              >
                Add Fact
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-4">
            <Input
              label="Key"
              placeholder="e.g. price"
              value={form.key}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              autoFocus
            />
            <Input
              label="Value"
              placeholder="e.g. $99/month"
              value={form.value}
              onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
            />
            <Input
              label="Source (optional)"
              placeholder="e.g. pricing.pdf"
              value={form.source}
              onChange={(e) =>
                setForm((f) => ({ ...f, source: e.target.value }))
              }
            />
            {addMutation.error && (
              <p className="text-xs text-red-500">
                {(addMutation.error as Error).message}
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function FactRow({
  fact,
  onDelete,
  deleting,
}: {
  fact: KBFact;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <tr className="hover:bg-gray-50 transition-colors group">
      <td className="px-4 py-3 font-mono text-xs text-indigo-700 font-medium">
        {fact.key}
      </td>
      <td className="px-4 py-3 text-gray-800">{fact.value}</td>
      <td className="px-4 py-3 text-gray-400 text-xs">{fact.source ?? "—"}</td>
      <td className="px-4 py-3">
        <button
          onClick={onDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-500 transition-all"
        >
          <Trash2 size={13} />
        </button>
      </td>
    </tr>
  );
}

/* ── Limitations tab ───────────────────────────────────────────────────────── */

function LimitationsTab({ kbId, onMutate }: { kbId: string; onMutate: () => void }) {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [description, setDescription] = useState("");

  const { data: limitations, isLoading } = useQuery({
    queryKey: ["kbs", kbId, "limitations"],
    queryFn: () => kbApi.listLimitations(kbId),
  });

  const addMutation = useMutation({
    mutationFn: () => kbApi.addLimitation(kbId, { description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs", kbId, "limitations"] });
      onMutate();
      setShowAdd(false);
      setDescription("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (limId: string) => kbApi.deleteLimitation(kbId, limId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs", kbId, "limitations"] });
      onMutate();
    },
  });

  return (
    <>
      <div className="flex justify-end mb-4">
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus size={13} />}
          onClick={() => setShowAdd(true)}
        >
          Add Limitation
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : !limitations?.length ? (
        <EmptyState
          icon={<AlertCircle size={40} />}
          title="No limitations documented"
          description='Add "does NOT do" entries so the AI can decline accurately instead of hallucinating a capability.'
          action={
            <Button
              size="sm"
              icon={<Plus size={13} />}
              onClick={() => setShowAdd(true)}
            >
              Add First Limitation
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {limitations.map((lim) => (
            <LimRow
              key={lim.id}
              lim={lim}
              onDelete={() => deleteMutation.mutate(lim.id)}
              deleting={deleteMutation.isPending}
            />
          ))}
        </div>
      )}

      {showAdd && (
        <Modal
          title="Add Limitation"
          onClose={() => setShowAdd(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setShowAdd(false)}>
                Cancel
              </Button>
              <Button
                loading={addMutation.isPending}
                disabled={!description.trim()}
                onClick={() => addMutation.mutate()}
              >
                Add
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-4">
            <Textarea
              label="Description"
              placeholder="e.g. Does not support real-time data feeds"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              autoFocus
              hint="Write in plain language — this is what the AI reads to know what NOT to claim"
            />
            {addMutation.error && (
              <p className="text-xs text-red-500">
                {(addMutation.error as Error).message}
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function LimRow({
  lim,
  onDelete,
  deleting,
}: {
  lim: KBLimitation;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div className="flex items-start gap-3 bg-white border border-gray-200 rounded-xl px-4 py-3 group hover:shadow-sm transition-shadow">
      <span className="text-amber-400 mt-0.5 shrink-0">
        <AlertCircle size={14} />
      </span>
      <p className="text-sm text-gray-700 flex-1">{lim.description}</p>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-gray-300">{ago(lim.created_at)}</span>
        <button
          onClick={onDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1 text-gray-300 hover:text-red-500 transition-all"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { KB, ago, kbApi } from "../api/kbs";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import EmptyState from "../components/ui/EmptyState";
import Input from "../components/ui/Input";
import Modal from "../components/ui/Modal";
import Spinner from "../components/ui/Spinner";

export default function KBsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", owner: "" });
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KB | null>(null);

  const { data: kbs, isLoading } = useQuery({
    queryKey: ["kbs"],
    queryFn: kbApi.list,
  });

  const createMutation = useMutation({
    mutationFn: kbApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      setShowCreate(false);
      setForm({ name: "", owner: "" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => kbApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kbs"] });
      setDeleteTarget(null);
    },
  });

  return (
    <>
      {/* Page header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">
            Knowledge Bases
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Standalone, versioned sources of truth attached to your projects
          </p>
        </div>
        <Button
          icon={<Plus size={15} />}
          onClick={() => setShowCreate(true)}
        >
          New Knowledge Base
        </Button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center pt-20">
          <Spinner size="lg" />
        </div>
      ) : !kbs?.length ? (
        <EmptyState
          icon={<Database size={48} />}
          title="No knowledge bases yet"
          description="Create a knowledge base to store documents, facts, and limitations for your AI presenter."
          action={
            <Button icon={<Plus size={15} />} onClick={() => setShowCreate(true)}>
              Create Knowledge Base
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {kbs.map((kb) => (
            <KBCard
              key={kb.id}
              kb={kb}
              menuOpen={menuOpen === kb.id}
              onMenuToggle={() =>
                setMenuOpen(menuOpen === kb.id ? null : kb.id)
              }
              onOpen={() => navigate(`/kbs/${kb.id}`)}
              onDelete={() => {
                setMenuOpen(null);
                setDeleteTarget(kb);
              }}
            />
          ))}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <Modal
          title="New Knowledge Base"
          onClose={() => {
            setShowCreate(false);
            setForm({ name: "", owner: "" });
          }}
          footer={
            <>
              <Button
                variant="secondary"
                onClick={() => setShowCreate(false)}
              >
                Cancel
              </Button>
              <Button
                loading={createMutation.isPending}
                disabled={!form.name.trim() || !form.owner.trim()}
                onClick={() => createMutation.mutate(form)}
              >
                Create
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-4">
            <Input
              label="Name"
              placeholder="e.g. Product Knowledge Base"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              autoFocus
            />
            <Input
              label="Owner"
              placeholder="e.g. alice"
              value={form.owner}
              onChange={(e) =>
                setForm((f) => ({ ...f, owner: e.target.value }))
              }
            />
            {createMutation.error && (
              <p className="text-xs text-red-500">
                {(createMutation.error as Error).message}
              </p>
            )}
          </div>
        </Modal>
      )}

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <Modal
          title="Delete Knowledge Base"
          onClose={() => setDeleteTarget(null)}
          size="sm"
          footer={
            <>
              <Button
                variant="secondary"
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                loading={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(deleteTarget.id)}
              >
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm text-gray-600">
            Are you sure you want to delete{" "}
            <span className="font-semibold text-gray-900">
              {deleteTarget.name}
            </span>
            ? All documents, facts, and limitations will be permanently removed.
          </p>
        </Modal>
      )}
    </>
  );
}

function KBCard({
  kb,
  menuOpen,
  onMenuToggle,
  onOpen,
  onDelete,
}: {
  kb: KB;
  menuOpen: boolean;
  onMenuToggle: () => void;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow cursor-pointer group relative"
      onClick={onOpen}
    >
      {/* Header row */}
      <div className="flex items-start justify-between mb-3">
        <div className="w-9 h-9 bg-indigo-50 rounded-lg flex items-center justify-center">
          <Database size={18} className="text-indigo-600" />
        </div>
        {/* Menu button — stop propagation so card click doesn't fire */}
        <div className="relative" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={onMenuToggle}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors opacity-0 group-hover:opacity-100"
          >
            <MoreHorizontal size={15} />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-8 w-36 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-10">
              <button
                onClick={onDelete}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
              >
                <Trash2 size={13} />
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Name & owner */}
      <h3 className="font-semibold text-gray-900 text-sm mb-0.5 truncate">
        {kb.name}
      </h3>
      <p className="text-xs text-gray-400 mb-4">by {kb.owner}</p>

      {/* Stats */}
      <div className="flex items-center gap-1.5 flex-wrap mb-3">
        <Badge variant="indigo">v{kb.version}</Badge>
        <span className="text-gray-200 text-xs">·</span>
        <span className="text-xs text-gray-400 font-mono truncate">
          {kb.content_hash}
        </span>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <span className="text-xs text-gray-400">
          Updated {ago(kb.updated_at)}
        </span>
        <span className="text-xs font-medium text-indigo-600 group-hover:underline">
          Open →
        </span>
      </div>
    </div>
  );
}

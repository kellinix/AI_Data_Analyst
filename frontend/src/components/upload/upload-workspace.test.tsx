// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { UploadedFile } from "@/types"
import { UploadWorkspace } from "./upload-workspace"

const state = vi.hoisted(() => ({
  files: [] as File[],
  upload: vi.fn<(file: File) => Promise<UploadedFile>>(),
  single: vi.fn<(body: Record<string, unknown>) => Promise<never>>(() => new Promise(() => {})),
  combined: vi.fn<(body: Record<string, unknown>) => Promise<never>>(() => new Promise(() => {})),
}))

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
vi.mock("@/components/upload/upload-zone", () => ({ UploadZone: ({ onFilesAccepted }: { onFilesAccepted: (files: File[]) => void }) =>
  <button onClick={() => onFilesAccepted(state.files)}>Choose data files</button> }))
vi.mock("@/components/upload/processing-animation", () => ({ ProcessingAnimation: () => null }))
vi.mock("@/hooks/use-analyses", () => ({
  useCreateAnalysis: () => ({ mutateAsync: state.single }),
  useCreateCombinedAnalysis: () => ({ mutateAsync: state.combined }),
}))
vi.mock("@/lib/api/uploads", () => ({ uploadsApi: { uploadFile: state.upload } }))

const guide = { version: 1, fields: [{ source_table: "people.csv", source_column: "status", label: "Marital status",
  values: [{ value: "M", label: "Married" }] }] }

function guideFile(text: string): File {
  const file = new File([text], "source-guide.json", { type: "application/json" })
  Object.defineProperty(file, "text", { value: async () => text })
  return file
}

beforeEach(() => {
  state.files = [new File(["id,status\n1,M"], "people.csv", { type: "text/csv" })]
  state.single.mockClear()
  state.combined.mockClear()
  state.upload.mockReset().mockImplementation(async (file) => ({
    id: file.name, original_filename: file.name, filename: file.name, user_id: "test", file_size: file.size,
    mime_type: "text/csv", storage_path: "", row_count: 1, column_count: 2, created_at: "",
    columns: ["id", "status"].map((name) => ({ name, dtype: "String", non_null_count: 1,
      null_count: 0, unique_count: 1, sample_values: [] })),
  }))
})
afterEach(cleanup)

it.each([1, 2])("attaches a separate guide to a normal %s-file analysis", async (fileCount) => {
  if (fileCount === 2) state.files.push(new File(["id,amount\n1,10"], "gifts.csv", { type: "text/csv" }))
  render(<UploadWorkspace />)
  fireEvent.click(screen.getByRole("button", { name: "Choose data files" }))
  fireEvent.change(screen.getByLabelText("Data guide (optional)"), { target: { files: [guideFile(JSON.stringify(guide))] } })
  await waitFor(() => expect(screen.getByText(/source-guide.json.*1 field definition/)).toBeTruthy())
  fireEvent.click(screen.getByRole("button", { name: "Review relationships" }))
  await waitFor(() => expect(screen.getByRole("button", { name: "Start analysis" })).toBeTruthy())
  fireEvent.click(screen.getByRole("button", { name: "Start analysis" }))
  const creator = fileCount === 1 ? state.single : state.combined
  await waitFor(() => expect(creator).toHaveBeenCalledOnce())
  const request = creator.mock.calls[0][0] as {
    file_id?: string; file_ids?: string[]; relationship_context: { data_dictionary: unknown }
  }
  expect(request.relationship_context.data_dictionary).toEqual(guide)
  expect(request.file_ids ?? [request.file_id]).toEqual(state.files.map((file) => file.name))
  expect(state.upload.mock.calls.map(([file]) => file.name)).toEqual(state.files.map((file) => file.name))
})

it("keeps an invalid guide out of data uploads and allows it to be removed", async () => {
  render(<UploadWorkspace />)
  fireEvent.click(screen.getByRole("button", { name: "Choose data files" }))
  fireEvent.change(screen.getByLabelText("Data guide (optional)"), { target: { files: [guideFile("{bad")] } })
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("valid JSON guide"))
  expect(screen.getByRole("button", { name: "Review relationships" }).hasAttribute("disabled")).toBe(true)
  expect(state.upload).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Remove data guide" }))
  fireEvent.click(screen.getByRole("button", { name: "Review relationships" }))
  await waitFor(() => expect(state.upload).toHaveBeenCalledOnce())
  expect(state.upload.mock.calls[0][0].name).toBe("people.csv")
})

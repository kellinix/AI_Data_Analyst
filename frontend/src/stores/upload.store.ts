import { create } from "zustand"

interface UploadState {
  files: File[]
  uploadProgress: Record<string, number>
  isUploading: boolean
  addFiles: (files: File[]) => void
  removeFile: (name: string) => void
  setProgress: (name: string, progress: number) => void
  setUploading: (uploading: boolean) => void
  reset: () => void
}

export const useUploadStore = create<UploadState>((set) => ({
  files: [],
  uploadProgress: {},
  isUploading: false,
  addFiles: (files) =>
    set((state) => ({
      files: [
        ...state.files,
        ...files.filter(
          (f) => !state.files.some((existing) => existing.name === f.name)
        ),
      ],
    })),
  removeFile: (name) =>
    set((state) => ({
      files: state.files.filter((f) => f.name !== name),
      uploadProgress: Object.fromEntries(
        Object.entries(state.uploadProgress).filter(([k]) => k !== name)
      ),
    })),
  setProgress: (name, progress) =>
    set((state) => ({
      uploadProgress: { ...state.uploadProgress, [name]: progress },
    })),
  setUploading: (isUploading) => set({ isUploading }),
  reset: () => set({ files: [], uploadProgress: {}, isUploading: false }),
}))

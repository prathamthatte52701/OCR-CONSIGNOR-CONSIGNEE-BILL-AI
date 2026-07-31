import { create } from "zustand";

// severity: "normal" | "warning" | "critical" - drives ConfirmDialog's visual treatment.
export const useDialogStore = create((set, get) => ({
  dialog: null,

  confirm: ({ title, message, severity = "normal", confirmLabel = "Confirm", requirePhrase = null }) =>
    new Promise((resolve) => {
      set({
        dialog: {
          title,
          message,
          severity,
          confirmLabel,
          requirePhrase,
          onConfirm: () => {
            set({ dialog: null });
            resolve(true);
          },
          onCancel: () => {
            set({ dialog: null });
            resolve(false);
          },
        },
      });
    }),

  close: () => {
    const { dialog } = get();
    dialog?.onCancel?.();
  },
}));

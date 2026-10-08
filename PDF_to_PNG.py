import tkinter as tk
from tkinter import filedialog, messagebox
import fitz  # PyMuPDF
from PIL import Image, ImageTk

class VisualPDFCropper:
    def __init__(self, root):
        self.root = root
        self.root.title("Visual PDF Crop & Combine Tool - Web Optimized")
        self.root.geometry("1100x800")

        # Application state
        self.doc = None
        self.current_page = 0
        self.scale = 1.0  
        self.snippets = []
        self.web_dpi = 150  # Optimized for crisp web rendering without aggressive downscaling

        # --- Top Controls Bar ---
        controls = tk.Frame(root, pady=8, padx=8)
        controls.pack(fill=tk.X, side=tk.TOP)

        # File & Navigation
        tk.Button(controls, text="1. Open PDF", command=self.load_pdf, font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=4)
        tk.Button(controls, text="◀ Prev", command=self.prev_page).pack(side=tk.LEFT, padx=2)
        tk.Button(controls, text="Next ▶", command=self.next_page).pack(side=tk.LEFT, padx=2)
        
        self.page_label = tk.Label(controls, text="Page: -/-", font=("Arial", 10))
        self.page_label.pack(side=tk.LEFT, padx=8)

        # Zoom Controls
        tk.Button(controls, text="Zoom -", command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        tk.Button(controls, text="Zoom +", command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        tk.Button(controls, text="Fit Window", command=self.fit_to_window).pack(side=tk.LEFT, padx=2)

        # Selection & Clear Buttons
        tk.Button(controls, text="Clear Box", command=self.clear_box_selection, bg="#f8d7da", fg="#842029").pack(side=tk.LEFT, padx=6)
        tk.Button(controls, text="2. Add Selected Region", command=self.add_crop_snippet, bg="#d1e7dd").pack(side=tk.LEFT, padx=6)
        
        self.snippets_label = tk.Label(controls, text="Snippets: 0", font=("Arial", 10, "bold"), fg="#0d6efd")
        self.snippets_label.pack(side=tk.LEFT, padx=8)

        tk.Button(controls, text="Clear All Snippets", command=self.clear_all_snippets, bg="#dc3545", fg="white").pack(side=tk.LEFT, padx=4)
        tk.Button(controls, text="3. Export Web PNG", command=self.export_png, bg="#0d6efd", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=6)

        # --- Canvas Container with Scrollbars ---
        canvas_frame = tk.Frame(root)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.v_scrollbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.h_scrollbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(
            canvas_frame, 
            cursor="cross", 
            bg="#555555",
            xscrollcommand=self.h_scrollbar.set,
            yscrollcommand=self.v_scrollbar.set
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.v_scrollbar.config(command=self.canvas.yview)
        self.h_scrollbar.config(command=self.canvas.xview)

        # Bind Mouse Events
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.start_x = self.start_y = self.end_x = self.end_y = None
        self.rect_id = None
        self.tk_img = None

    def load_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not file_path:
            return
        self.doc = fitz.open(file_path)
        self.current_page = 0
        self.fit_to_window()

    def display_page(self):
        if not self.doc:
            return
        
        page = self.doc.load_page(self.current_page)
        self.page_label.config(text=f"Page: {self.current_page + 1} / {len(self.doc)}")

        mat = fitz.Matrix(self.scale, self.scale)
        pix = page.get_pixmap(matrix=mat)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_img = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.rect_id = None

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.display_page()

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.display_page()

    def zoom_in(self):
        self.scale *= 1.2
        self.display_page()

    def zoom_out(self):
        self.scale /= 1.2
        self.display_page()

    def fit_to_window(self):
        if not self.doc:
            return
        self.root.update_idletasks()
        page = self.doc.load_page(self.current_page)
        page_rect = page.rect

        canvas_width = self.canvas.winfo_width() - 20
        canvas_height = self.canvas.winfo_height() - 20

        if canvas_width > 100 and canvas_height > 100:
            scale_x = canvas_width / page_rect.width
            scale_y = canvas_height / page_rect.height
            self.scale = min(scale_x, scale_y)
        else:
            self.scale = 1.0

        self.display_page()

    def clear_box_selection(self):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None
        self.start_x = self.start_y = self.end_x = self.end_y = None

    def clear_all_snippets(self):
        if not self.snippets:
            return
        if messagebox.askyesno("Clear All", "Are you sure you want to remove all saved image snippets?"):
            self.snippets.clear()
            self.snippets_label.config(text="Snippets: 0")
            self.clear_box_selection()
            messagebox.showinfo("Cleared", "All captured snippets have been cleared.")

    def on_press(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2
        )

    def on_drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        self.end_x = self.canvas.canvasx(event.x)
        self.end_y = self.canvas.canvasy(event.y)

    def add_crop_snippet(self):
        if not self.doc or self.start_x is None or self.end_x is None:
            messagebox.showwarning("Selection Missing", "Please load a PDF and drag a red bounding box first.")
            return

        x0 = min(self.start_x, self.end_x) / self.scale
        y0 = min(self.start_y, self.end_y) / self.scale
        x1 = max(self.start_x, self.end_x) / self.scale
        y1 = max(self.start_y, self.end_y) / self.scale

        page = self.doc.load_page(self.current_page)
        rect = fitz.Rect(x0, y0, x1, y1)
        
        # Capture selected box at 150 DPI (Web Optimized)
        pix = page.get_pixmap(clip=rect, dpi=self.web_dpi)

        snippet = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.snippets.append(snippet)
        
        self.snippets_label.config(text=f"Snippets: {len(self.snippets)}")
        self.clear_box_selection()

    def export_png(self):
        if not self.snippets:
            messagebox.showwarning("Empty", "No cropped sections added to export yet.")
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png")])
        if not save_path:
            return

        max_width = max(img.width for img in self.snippets)
        total_height = sum(img.height for img in self.snippets)

        combined_image = Image.new("RGB", (max_width, total_height), (255, 255, 255))

        y_offset = 0
        for img in self.snippets:
            combined_image.paste(img, (0, y_offset))
            y_offset += img.height

        # EXPORT FIXES FOR GOOGLE CLOUD:
        # 1. Provide exact DPI metadata (150, 150)
        # 2. Use optimize=True to compress file size for web without losing sharpness
        combined_image.save(save_path, "PNG", dpi=(self.web_dpi, self.web_dpi), optimize=True)
        
        messagebox.showinfo("Saved!", f"Web-Optimized PNG exported successfully to:{save_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VisualPDFCropper(root)
    root.mainloop()

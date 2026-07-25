import SwiftUI

struct NewApplicationView: View {
    var viewModel: ApplicationsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var firma = ""
    @State private var rolle = ""
    @State private var ort = ""
    @State private var isHeadhunter = false
    @State private var errorMessage: String?
    @State private var isSaving = false

    var body: some View {
        NavigationStack {
            Form {
                TextField("Company", text: $firma)
                TextField("Role", text: $rolle)
                TextField("Location", text: $ort)
                Toggle("Via headhunter", isOn: $isHeadhunter)

                if let errorMessage {
                    Text(errorMessage).foregroundStyle(.red)
                }
            }
            .navigationTitle("New application")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .disabled(firma.isEmpty || rolle.isEmpty || isSaving)
                }
            }
        }
    }

    private func save() {
        isSaving = true
        errorMessage = nil
        Task {
            do {
                let payload = ApplicationCreatePayload(
                    firma: firma, rolle: rolle, isHeadhunter: isHeadhunter,
                    ort: ort.isEmpty ? nil : ort
                )
                _ = try await viewModel.create(payload)
                dismiss()
            } catch let error as APIError {
                errorMessage = error.message
            } catch {
                errorMessage = error.localizedDescription
            }
            isSaving = false
        }
    }
}

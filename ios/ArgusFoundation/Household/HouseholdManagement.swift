import SwiftUI
import ArgusSession

struct HouseholdManagement: View {
    @ObservedObject var model: HouseholdModel
    var accounts: AccountsModel?
    @Environment(\.dismiss) private var dismiss
    @State private var sharing: FinancialAccount?
    @State private var confirmation: HouseholdAction?
    @Environment(\.locale) private var locale
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    var body: some View {
        NavigationStack {
            Form {
                if let error = model.errorKey { Text(LocalizedStringKey(error)).foregroundStyle(ArgusStyle.secondary).accessibilityIdentifier("household.management.error") }
                if model.pending != nil {
                    Section { Text("household.uncertain"); Button("accounts.retry") { Task { await model.retry() } }.accessibilityIdentifier("household.pending.retry") }
                }
                if let household = model.household, !model.joiningByInvitation {
                    Section(household.name ?? NSLocalizedString("household.title", comment: "")) {
                        Text("household.consent").font(.footnote)
                        ForEach(household.members) { member in
                            HStack {
                                Text(member.displayName).accessibilityIdentifier("household.member.name." + member.id.uuidString)
                                Spacer()
                                if member.isAdmin { Text("household.admin").foregroundStyle(.secondary) }
                                if household.isAdmin && !member.isSelf {
                                    Menu {
                                        Button("household.transferAdmin") { confirmation = HouseholdAction(suffix: "/transfer-admin", member: member.userId, title: "household.transferAdmin") }
                                        Button("household.remove", role: .destructive) { confirmation = HouseholdAction(suffix: "/members/" + member.userId.uuidString + "/remove", title: "household.remove") }
                                    } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }.accessibilityLabel("household.manageMember")
                                }
                            }.accessibilityIdentifier("household.member." + member.id.uuidString)
                        }
                    }
                    if household.isAdmin {
                        Section("household.invitations") {
                            Button("household.prepareInvite") { Task { await model.versionCommand("/invitations") } }.accessibilityIdentifier("household.invite")
                            if let invitation = model.invitation {
                                HouseholdInvitationShareView(invitation: invitation, spanish: spanish)
                            }
                            ForEach(household.invitations) { invitation in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(LocalizedStringKey("household.invitation." + invitation.state))
                                        Text(invitation.expiresAt).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if invitation.state == "pending" {
                                        Button("household.revoke", role: .destructive) { Task { await model.versionCommand("/invitations/" + invitation.id.uuidString + "/revoke") } }.accessibilityIdentifier("household.invite.revoke." + invitation.id.uuidString)
                                    }
                                }
                            }
                        }
                    }
                    Section("household.shareAccounts") {
                        Text("household.shareExplanation").font(.footnote)
                        ForEach(accounts?.accounts ?? []) { account in
                            Button { sharing = account } label: {
                                HStack { Text(account.nickname ?? account.type); Spacer(); if household.shares.contains(where: { $0.accountId == account.id }) { Text("household.shared").foregroundStyle(.secondary) } }
                            }.accessibilityIdentifier("household.share.account." + account.id.uuidString)
                        }
                    }
                    Section {
                        Text("household.departureNotice").font(.footnote)
                        Text("sharedPlan.departureNotice").font(.footnote).accessibilityIdentifier("sharedPlan.departureNotice")
                        if household.isAdmin {
                            Text("household.adminDeparture").font(.footnote)
                            Button("household.close", role: .destructive) { confirmation = HouseholdAction(suffix: "/close", title: "household.close") }.accessibilityIdentifier("household.close")
                        } else {
                            Button("household.leave", role: .destructive) { confirmation = HouseholdAction(suffix: "/leave", title: "household.leave") }.accessibilityIdentifier("household.leave")
                        }
                    }
                }
                if model.household == nil || model.joiningByInvitation {
                    HouseholdIntroduction(model: model)
                }

            }
            .scrollContentBackground(.hidden)
            .background(WelcomePalette.background)
            .tint(WelcomePalette.pine)
            .disabled(model.busy)
            .navigationTitle(model.household == nil ? "household.title" : "household.people")
            .toolbar { CuadraoDoneToolbar(title: "action.close", identifier: "household.management.done") { dismiss() }}
            .task { await accounts?.load(); await model.refresh() }
            .sheet(item: $sharing) { HouseholdShareSheet(model: model, account: $0) }
            .confirmationDialog(confirmation.map { LocalizedStringKey($0.title) } ?? "household.manage", isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } }), titleVisibility: .visible) {
                if let action = confirmation { Button(LocalizedStringKey(action.title), role: .destructive) { Task { await model.versionCommand(action.suffix, member: action.member); confirmation = nil } } }
                Button("accounts.cancel", role: .cancel) { confirmation = nil }
            } message: { VStack { Text("household.departureNotice"); Text("sharedPlan.departureNotice") } }
        }
    }
}
private struct HouseholdAction { let suffix: String; var member: UUID? = nil; let title: String }

struct HouseholdShareSheet: View {
    @ObservedObject var model: HouseholdModel
    let account: FinancialAccount
    @Environment(\.dismiss) private var dismiss
    @State private var selected: Set<UUID> = []
    @State private var editors: Set<UUID> = []
    var body: some View {
        NavigationStack {
            Form {
                Section(account.nickname ?? account.type) {
                    Text("household.shareExplanation")
                    ForEach(model.household?.members.filter { !$0.isSelf } ?? []) { member in
                        Toggle(member.displayName, isOn: Binding(get: { selected.contains(member.id) }, set: { if $0 { selected.insert(member.id) } else { selected.remove(member.id); editors.remove(member.id) } })).accessibilityIdentifier("household.share.member." + member.id.uuidString)
                        if selected.contains(member.id) {
                            Toggle("household.allowEditing", isOn: Binding(get: { editors.contains(member.id) }, set: { if $0 { editors.insert(member.id) } else { editors.remove(member.id) } })).accessibilityIdentifier("household.share.edit." + member.id.uuidString)
                        }
                    }
                    Text("household.editExplanation").font(.footnote)
                }
                if let error = model.errorKey { Text(LocalizedStringKey(error)) }
                Button("household.confirmShare") {
                    Task {
                        await model.versionCommand("/accounts/" + account.id.uuidString + "/grants", method: "PUT", recipients: selected.sorted { $0.uuidString < $1.uuidString }.map { HouseholdRecipient(membershipId: $0, permission: editors.contains($0) ? "edit" : "view") })
                        if model.pending == nil && model.errorKey == nil { dismiss() }
                    }
                }.disabled(model.busy || model.pending != nil).accessibilityIdentifier("household.share.confirm")
                if model.household?.shares.contains(where: { $0.accountId == account.id }) == true {
                    Button("household.withdraw", role: .destructive) { Task { await model.versionCommand("/accounts/" + account.id.uuidString + "/grants", method: "PUT", recipients: []); if model.pending == nil && model.errorKey == nil { dismiss() } } }.accessibilityIdentifier("household.share.withdraw")
                }
            }
            .navigationTitle("household.shareAccounts")
            .toolbar { CuadraoCancelToolbar(title: "accounts.cancel") { dismiss() } }
            .onAppear {
                if let share = model.household?.shares.first(where: { $0.accountId == account.id }) {
                    selected = Set(share.recipients.map(\.membershipId)); editors = Set(share.recipients.filter { $0.permission == "edit" }.map(\.membershipId))
                }
            }
        }
    }
}

struct HouseholdIntroduction: View {
    @ObservedObject var model: HouseholdModel
    @Environment(\.dismiss) private var dismiss
    @State private var mode = "intro"
    @State private var name = ""
    @State private var displayName = ""
    @State private var token = ""
    @State private var handedOver = ""
    var body: some View {
        Group {
            Section {
                Text("household.introductionTitle").font(ArgusStyle.display(25))
                Text("household.consent")
                Text("household.inviteWhenReady").font(.footnote)
            }
            if mode == "intro" {
                Section {
                    Button("household.create") { mode = "create" }.accessibilityIdentifier("household.intro.create")
                    Button("household.join") { mode = "join" }.accessibilityIdentifier("household.intro.join")
                    ForEach(model.households) { household in Button(household.name ?? NSLocalizedString("household.title", comment: "")) { Task { await model.select(household.id) } }.accessibilityIdentifier("household.open." + household.id.uuidString) }
                }
            }
            if mode == "create" {
                Section("household.create") {
                    TextField("household.name", text: $name).accessibilityIdentifier("household.name")
                    TextField("household.yourName", text: $displayName).accessibilityIdentifier("household.displayName")
                    Button("household.create") { Task { await model.command(HouseholdCommand(name: name, displayName: displayName), path: "") } }.disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || displayName.trimmingCharacters(in: .whitespaces).isEmpty).accessibilityIdentifier("household.create")
                }
            }
            if mode == "join" {
                Section("household.join") {
                    TextField("household.pasteInvite", text: $token).textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("household.invite.input").onChange(of: token) { _, value in
                        if value != handedOver { handedOver = ""; model.cancelInvitationReview() }
                    }
                    HouseholdInvitationEntryHint()
                    Button("household.reviewInvite") { Task { await model.previewInvitation(token) } }.disabled(token.isEmpty).accessibilityIdentifier("household.invite.preview")
                    if let preview = model.invitationPreview {
                        Text(preview.name ?? NSLocalizedString("household.title", comment: "")).font(.headline)
                        Text("household.consent").font(.footnote)
                        if preview.available {
                            TextField("household.yourName", text: $displayName).accessibilityIdentifier("household.join.displayName")
                            Button("household.accept") { Task { await model.acceptInvitation(displayName: displayName) } }.disabled(displayName.isEmpty).accessibilityIdentifier("household.accept")
                        } else { Text("household.inviteUnavailable") }
                        Button("household.notNow") { dismiss() }.accessibilityIdentifier("household.notNow")
                    }
                    if let problem = model.invitationProblem { HouseholdInvitationProblemText(problem: problem) }
                }
            }
            if mode != "intro" { Button("accounts.back") { mode = "intro" }.frame(minHeight: 44) }
        }.onAppear {
            displayName = model.identity?.profile?.displayName ?? ""
            adoptHandedOver()
        }.onChange(of: model.pendingInvitationToken) { adoptHandedOver() }
    }
    /// A code handed over by link or by the beta gate fills the field whether it arrives before or after the introduction appears.
    private func adoptHandedOver() {
        guard !model.pendingInvitationToken.isEmpty else { return }
        let input = model.pendingInvitationToken
        handedOver = input; token = input; mode = "join"; model.pendingInvitationToken = ""
    }
}

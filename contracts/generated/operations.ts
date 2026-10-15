// GENERATED. Use with your shared authenticated HTTP transport.
import type * as T from "./types";
export interface Operations {
  health: { request: undefined; response: T.Health };
  capabilities: { request: undefined; response: T.Capabilities };
  login: { request: T.Login; response: T.Auth };
  refresh: { request: undefined; response: T.Auth };
  logout: { request: undefined; response: undefined };
  currentUser: { request: undefined; response: T.User };
  myTeam: { request: undefined; response: T.Team };
  updateMyTeam: { request: T.TeamPatch; response: T.Team };
  setActiveBot: { request: T.SetActiveBot; response: T.ActiveBot };
  listOpponents: { request: undefined; response: T.TeamPublicPage };
  createSubmission: { request: T.Upload; response: T.SubmissionAccepted };
  listSubmissions: { request: undefined; response: T.SubmissionPage };
  getSubmission: { request: undefined; response: T.Submission };
  getBuildLog: { request: undefined; response: T.BuildLog };
  getOwnSource: { request: undefined; response: T.SourceTree };
  getOwnSourceFile: { request: undefined; response: T.SourceFile };
  createScrimmage: { request: T.ScrimmageCreate; response: T.MatchAccepted };
  listScrimmages: { request: undefined; response: T.MatchPage };
  scrimmageQuota: { request: undefined; response: T.Quota };
  listMatches: { request: undefined; response: T.MatchPage };
  getMatch: { request: undefined; response: T.Match };
  getGame: { request: undefined; response: T.Game };
  getReplayUrl: { request: undefined; response: T.SignedUrl };
  getStandings: { request: undefined; response: T.StandingPage };
  getBracket: { request: undefined; response: T.BracketSlotPage };
  listTournaments: { request: undefined; response: T.TournamentPage };
  getTournament: { request: undefined; response: T.Tournament };
  listRounds: { request: undefined; response: T.RoundPage };
  listAnnouncements: { request: undefined; response: T.AnnouncementPage };
  getDocs: { request: undefined; response: T.Docs };
  adminListTeams: { request: undefined; response: T.TeamPage };
  adminCreateTeam: { request: T.TeamCreate; response: T.Team };
  adminUpdateTeam: { request: T.AdminTeamPatch; response: T.Team };
  adminImportTeams: { request: T.ImportRequest; response: T.ImportResult };
  adminListSubmissions: { request: undefined; response: T.SubmissionPage };
  adminGetSubmission: { request: undefined; response: T.Submission };
  adminGetSource: { request: undefined; response: T.SourceTree };
  adminGetSourceFile: { request: undefined; response: T.SourceFile };
  adminBuildLog: { request: undefined; response: T.BuildLog };
  adminListTournaments: { request: undefined; response: T.TournamentPage };
  adminCreateTournament: { request: T.TournamentCreate; response: T.Tournament };
  adminGetDraw: { request: undefined; response: T.Draw };
  adminDraw: { request: T.DrawRequest; response: T.Draw };
  adminLockDraw: { request: T.ReasonBody; response: T.Draw };
  adminCreateRound: { request: T.RoundCreate; response: T.Round };
  adminListRounds: { request: undefined; response: T.RoundPage };
  adminUpdateRound: { request: T.RoundPatch; response: T.Round };
  adminFreezeRound: { request: T.ReasonBody; response: T.Snapshot };
  adminGetSnapshot: { request: undefined; response: T.Snapshot };
  adminRunRound: { request: T.ReasonBody; response: T.RunAccepted };
  adminListMatches: { request: undefined; response: T.MatchPage };
  adminGameLogs: { request: undefined; response: T.GameLogs };
  adminRerunGame: { request: T.ReasonBody; response: T.RerunAccepted };
  adminOverrideMatch: { request: T.Override; response: T.Match };
  adminQueue: { request: undefined; response: T.Queue };
  adminControlQueue: { request: T.QueueControl; response: T.Queue };
  adminSimilarity: { request: undefined; response: T.SimilarityPage };
  adminAuditLog: { request: undefined; response: T.AuditPage };
  adminAnnouncements: { request: undefined; response: T.AnnouncementPage };
  adminCreateAnnouncement: { request: T.AnnouncementWrite; response: T.Announcement };
  adminUpdateAnnouncement: { request: T.AnnouncementWrite; response: T.Announcement };
  adminPublishAnnouncement: { request: T.ReasonBody; response: T.Announcement };
  buildCallback: { request: T.BuildResult; response: T.Ack };
  gameCallback: { request: T.GameResultCallback; response: T.Ack };
  workerHeartbeat: { request: T.WorkerHeartbeat; response: T.Ack };
}
export const routes = {
  "health": {
    "method": "GET",
    "path": "/health",
    "status": 200
  },
  "capabilities": {
    "method": "GET",
    "path": "/capabilities",
    "status": 200
  },
  "login": {
    "method": "POST",
    "path": "/auth/login",
    "status": 200
  },
  "refresh": {
    "method": "POST",
    "path": "/auth/refresh",
    "status": 200
  },
  "logout": {
    "method": "POST",
    "path": "/auth/logout",
    "status": 204
  },
  "currentUser": {
    "method": "GET",
    "path": "/auth/me",
    "status": 200
  },
  "myTeam": {
    "method": "GET",
    "path": "/teams/me",
    "status": 200
  },
  "updateMyTeam": {
    "method": "PATCH",
    "path": "/teams/me",
    "status": 200
  },
  "setActiveBot": {
    "method": "PUT",
    "path": "/teams/me/active-bot",
    "status": 200
  },
  "listOpponents": {
    "method": "GET",
    "path": "/teams/opponents",
    "status": 200
  },
  "createSubmission": {
    "method": "POST",
    "path": "/submissions",
    "status": 202
  },
  "listSubmissions": {
    "method": "GET",
    "path": "/submissions",
    "status": 200
  },
  "getSubmission": {
    "method": "GET",
    "path": "/submissions/{id}",
    "status": 200
  },
  "getBuildLog": {
    "method": "GET",
    "path": "/submissions/{id}/build-log",
    "status": 200
  },
  "getOwnSource": {
    "method": "GET",
    "path": "/submissions/{id}/source",
    "status": 200
  },
  "getOwnSourceFile": {
    "method": "GET",
    "path": "/submissions/{id}/source-file",
    "status": 200
  },
  "createScrimmage": {
    "method": "POST",
    "path": "/scrimmages",
    "status": 202
  },
  "listScrimmages": {
    "method": "GET",
    "path": "/scrimmages",
    "status": 200
  },
  "scrimmageQuota": {
    "method": "GET",
    "path": "/scrimmages/quota",
    "status": 200
  },
  "listMatches": {
    "method": "GET",
    "path": "/matches",
    "status": 200
  },
  "getMatch": {
    "method": "GET",
    "path": "/matches/{id}",
    "status": 200
  },
  "getGame": {
    "method": "GET",
    "path": "/games/{id}",
    "status": 200
  },
  "getReplayUrl": {
    "method": "GET",
    "path": "/games/{id}/replay",
    "status": 200
  },
  "getStandings": {
    "method": "GET",
    "path": "/standings",
    "status": 200
  },
  "getBracket": {
    "method": "GET",
    "path": "/bracket",
    "status": 200
  },
  "listTournaments": {
    "method": "GET",
    "path": "/tournaments",
    "status": 200
  },
  "getTournament": {
    "method": "GET",
    "path": "/tournaments/{id}",
    "status": 200
  },
  "listRounds": {
    "method": "GET",
    "path": "/tournaments/{id}/rounds",
    "status": 200
  },
  "listAnnouncements": {
    "method": "GET",
    "path": "/announcements",
    "status": 200
  },
  "getDocs": {
    "method": "GET",
    "path": "/docs",
    "status": 200
  },
  "adminListTeams": {
    "method": "GET",
    "path": "/admin/teams",
    "status": 200
  },
  "adminCreateTeam": {
    "method": "POST",
    "path": "/admin/teams",
    "status": 201
  },
  "adminUpdateTeam": {
    "method": "PATCH",
    "path": "/admin/teams/{id}",
    "status": 200
  },
  "adminImportTeams": {
    "method": "POST",
    "path": "/admin/teams/import",
    "status": 201
  },
  "adminListSubmissions": {
    "method": "GET",
    "path": "/admin/submissions",
    "status": 200
  },
  "adminGetSubmission": {
    "method": "GET",
    "path": "/admin/submissions/{id}",
    "status": 200
  },
  "adminGetSource": {
    "method": "GET",
    "path": "/admin/submissions/{id}/source",
    "status": 200
  },
  "adminGetSourceFile": {
    "method": "GET",
    "path": "/admin/submissions/{id}/source-file",
    "status": 200
  },
  "adminBuildLog": {
    "method": "GET",
    "path": "/admin/submissions/{id}/build-log",
    "status": 200
  },
  "adminListTournaments": {
    "method": "GET",
    "path": "/admin/tournaments",
    "status": 200
  },
  "adminCreateTournament": {
    "method": "POST",
    "path": "/admin/tournaments",
    "status": 201
  },
  "adminGetDraw": {
    "method": "GET",
    "path": "/admin/tournaments/{id}/draw",
    "status": 200
  },
  "adminDraw": {
    "method": "POST",
    "path": "/admin/tournaments/{id}/draw",
    "status": 200
  },
  "adminLockDraw": {
    "method": "POST",
    "path": "/admin/tournaments/{id}/draw/lock",
    "status": 200
  },
  "adminCreateRound": {
    "method": "POST",
    "path": "/admin/tournaments/{id}/rounds",
    "status": 201
  },
  "adminListRounds": {
    "method": "GET",
    "path": "/admin/tournaments/{id}/rounds",
    "status": 200
  },
  "adminUpdateRound": {
    "method": "PATCH",
    "path": "/admin/rounds/{id}",
    "status": 200
  },
  "adminFreezeRound": {
    "method": "POST",
    "path": "/admin/rounds/{id}/freeze",
    "status": 200
  },
  "adminGetSnapshot": {
    "method": "GET",
    "path": "/admin/rounds/{id}/snapshot",
    "status": 200
  },
  "adminRunRound": {
    "method": "POST",
    "path": "/admin/rounds/{id}/run",
    "status": 202
  },
  "adminListMatches": {
    "method": "GET",
    "path": "/admin/matches",
    "status": 200
  },
  "adminGameLogs": {
    "method": "GET",
    "path": "/admin/games/{id}/logs",
    "status": 200
  },
  "adminRerunGame": {
    "method": "POST",
    "path": "/admin/games/{id}/rerun",
    "status": 202
  },
  "adminOverrideMatch": {
    "method": "POST",
    "path": "/admin/matches/{id}/override",
    "status": 200
  },
  "adminQueue": {
    "method": "GET",
    "path": "/admin/queue",
    "status": 200
  },
  "adminControlQueue": {
    "method": "PUT",
    "path": "/admin/queue",
    "status": 200
  },
  "adminSimilarity": {
    "method": "GET",
    "path": "/admin/similarity",
    "status": 200
  },
  "adminAuditLog": {
    "method": "GET",
    "path": "/admin/audit-log",
    "status": 200
  },
  "adminAnnouncements": {
    "method": "GET",
    "path": "/admin/announcements",
    "status": 200
  },
  "adminCreateAnnouncement": {
    "method": "POST",
    "path": "/admin/announcements",
    "status": 201
  },
  "adminUpdateAnnouncement": {
    "method": "PATCH",
    "path": "/admin/announcements/{id}",
    "status": 200
  },
  "adminPublishAnnouncement": {
    "method": "POST",
    "path": "/admin/announcements/{id}/publish",
    "status": 200
  },
  "buildCallback": {
    "method": "POST",
    "path": "/internal/builds/{id}",
    "status": 200
  },
  "gameCallback": {
    "method": "POST",
    "path": "/internal/games/{id}",
    "status": 200
  },
  "workerHeartbeat": {
    "method": "POST",
    "path": "/internal/workers/heartbeat",
    "status": 200
  }
} as const;

{
  lib,
  skillsDir ? ../skills,
}:
let
  skillEntries = builtins.readDir skillsDir;
  skillCategories = lib.sort builtins.lessThan (
    builtins.attrNames (
      lib.filterAttrs (
        name: type:
        type == "directory"
        && !(lib.hasPrefix "." name)
        && !(builtins.pathExists (skillsDir + "/${name}/SKILL.md"))
      ) skillEntries
    )
  );
in
{
  inherit skillCategories;

  watchSubpaths = [
    "rules"
    "skills"
  ]
  ++ map (cat: "skills/${cat}") skillCategories;

  fanout = [
    {
      from = "skills";
      into = [
        ".agents/skills"
        ".claude/skills"
      ];
      requireFile = "SKILL.md";
      recursive = true;
    }
  ];

  links = [
    {
      from = "rules/AGENTS.md";
      to = ".gemini/config/AGENTS.md";
    }
    {
      from = "rules/AGENTS.md";
      to = ".claude/CLAUDE.md";
    }
    {
      from = "rules/AGENTS.md";
      to = ".codex/AGENTS.md";
    }
    {
      from = "rules/AGENTS.md";
      to = ".config/opencode/AGENTS.md";
    }
    {
      from = "rules/AGENTS.md";
      to = ".gemini/GEMINI.md";
    }
  ];
}

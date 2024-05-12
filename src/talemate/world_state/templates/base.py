from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, TypeVar, Union
from typing_extensions import Annotated
import pydantic
import yaml
import os
import yaml
import structlog
import uuid

if TYPE_CHECKING:
    from talemate.config import Config
    

__all__ = [
    "register",
    "Template",
    "AnnotatedTemplate",
    "Group",
    "Collection",
    "FlatCollection",
    "TypedCollection"
]

log = structlog.get_logger("world-state.templates")

MODELS = {}
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "templates", "world-state")

class register:
    
    def __init__(self, template_type:str):
        self.template_type = template_type
        
    def __call__(self, cls):
        MODELS[self.template_type] = cls
        return cls
    
def name_to_id(name:str) -> str:
    return name.replace(" ", "_").lower()
    
def validate_template(v: Any, handler: pydantic.ValidatorFunctionWrapHandler, info: pydantic.ValidationInfo):
    if isinstance(v, dict):
        if v["template_type"] not in MODELS:
            raise ValueError(f"Template type {v['template_type']} is not registered")
        return MODELS[v["template_type"]](**v)
    elif isinstance(v, Template):
        if v.template_type not in MODELS:
            raise ValueError(f"Template type {v.template_type} is not registered")
        return v
    return handler(v)

class Template(pydantic.BaseModel):
    name: str
    template_type: str = "base"
    group: str | None = None
    favorite: bool = False
    uid: str = pydantic.Field(default_factory=lambda: str(uuid.uuid4()))
    
TemplateType = TypeVar("TemplateType", bound=Template)
AnnotatedTemplate = Annotated[TemplateType, pydantic.WrapValidator(validate_template)]
    
class Group(pydantic.BaseModel):
    author: str
    name: str
    description: str
    templates: dict[str, AnnotatedTemplate] = pydantic.Field(default_factory=dict)
    uid: str = pydantic.Field(default_factory=lambda: str(uuid.uuid4()))
    
    @classmethod
    def load(cls, path: str) -> "Group":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
            return cls(**data)
        
    @property
    def filename(self):
        cleaned_name = self.name.replace(" ", "-").lower()
        return f"{cleaned_name}.yaml"
    
    def save(self, path: str = TEMPLATE_PATH):
        path = os.path.join(path, self.filename)
            
        # ensure `group` is set on all templates
        for template in self.templates.values():
            template.group = self.uid
        
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, sort_keys=True)
        log.debug("Worldstate template group saved", path=path)
        
    def diff(self, group:"Group") -> "Group":
        """
        Will return a new group that contains only the templates that are
        different between the two groups
        
        New group will inherit name, author, and description from self.
        """
        templates = {}
        
        for template_id, template in self.templates.items():
            if template_id not in group.templates or not (self.templates[template_id] == group.templates[template_id]):
                templates[template_id] = template
            
        return Group(
            author=self.author,
            name=self.name,
            description=self.description,
            templates=templates
        )
                
    def insert(self, template:Template, save: bool = True):
        
        if template.uid in self.templates:
            raise ValueError(f"Template with id {template.uid} already exists in group")
        
        self.templates[template.uid] = template
        
        if save:
            self.save()
            
    def update(self, template:Template, save: bool = True):
        
        self.templates[template.uid] = template
        
        if save:
            self.save()
            
    def delete(self, template:Template, save: bool = True):
        if template.uid not in self.templates:
            return
        
        del self.templates[template.uid]
        
        if save:
            self.save()
    
    def find(self, uid:str) -> Template | None:
        for template in self.templates.values():
            if template.uid == uid:
                return template
        
        return None 

class Collection(pydantic.BaseModel):
    groups: list[Group] = pydantic.Field(default_factory=list)
    
    @classmethod
    def load(cls, path: str = TEMPLATE_PATH) -> "Collection":
        
        """
        Look for .yaml files in the given path and load them as groups
        into a new collection
        """
        
        groups = []
        
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".yaml"):
                    group = Group.load(os.path.join(root, file))
                    groups.append(group)
                    
        return cls(groups=groups)
        
    @classmethod
    def create_from_legacy_config(
        cls, 
        config:"Config", 
        save:bool=True, 
        check_if_exists:bool=True, 
        exclude:list[Group] = None
    ) -> "Collection":
        """
        templates used to be stored in the main tailmate config as 
        a dictionary of dictionaries. This method will convert those
        """
        
        groups = []
        
        config_templates = config.game.world_state.templates.model_dump()
        
        for template_type, templates in config_templates.items():
            
            name = f"legacy-{template_type.replace('_', '-')}s"
            
            if check_if_exists:
                if os.path.exists(os.path.join(TEMPLATE_PATH, f"{name}.yaml")):
                    log.debug("template transfer from legacy config", template_type=template_type, status="skipped", reason="already exists")
                    continue
            
            
            converted_templates = []
            for template in templates.values():
                converted_templates.append(MODELS[template_type](**template))           
            
            group = Group(
                author="unknown",
                name=name,
                description=f"Auto-generated group for {template_type} templates. This group was created from the legacy templates in the main talemate config file.",
                templates={
                    template.uid: template for template in converted_templates
                }
                #[MODELS[template_type](**template) for template in templates.values()]
            )
            
            if exclude:
                for _group in exclude:
                    group = group.diff(_group)
            
            groups.append(group)
            
            if save:
                group.save(TEMPLATE_PATH)
            
        collection = cls(groups=groups)
        
        return collection
    
    def flat(self, types: list[str] = None) -> "FlatCollection":
        """
        merged templates from all groups
        """
        
        templates = {}
        
        for group in self.groups:
            for template_id, template in group.templates.items():
                
                if types and template.template_type not in types:
                    continue
                
                uid = f"{group.uid}__{template_id}"
                templates[uid] = template
        
        return FlatCollection(templates=templates)
        
    def typed(self, types: list[str] = None) -> "TypedCollection":
        """
        Returns a dictionary of templates grouped by their template type
        """
        
        templates = {}
        
        for group in self.groups:
            for template_id, template in group.templates.items():
                
                if types and template.template_type not in types:
                    continue
                
                if template.template_type not in templates:
                    templates[template.template_type] = {}
                uid = f"{group.uid}__{template_id}"
                templates[template.template_type][uid] = template
                
        return TypedCollection(templates=templates)
    
    
    def save(self, path: str = TEMPLATE_PATH):
        for group in self.groups:
            group.save(path)
            
    def find(self, uid:str) ->  Group | None:
        for group in self.groups:
            if group.uid == uid:
                return group
        return None
            
class FlatCollection(pydantic.BaseModel):
    templates: dict[str, AnnotatedTemplate] = pydantic.Field(default_factory=dict)
    
class TypedCollection(pydantic.BaseModel):
    templates: dict[str, dict[str, AnnotatedTemplate]] = pydantic.Field(default_factory=dict)
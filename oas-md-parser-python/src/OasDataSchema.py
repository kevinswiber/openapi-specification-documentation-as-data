from OasData import Data
from OasDataVersion import DataVersion
import re
from MarkdownParser import ContentType
from MarkdownParser import ContentSubType
from OasDataUrl import DataWithUrls

class DataFieldType(Data):
  
  PARENT_TYPE_MAP='map'
  PARENT_TYPE_ARRAY='array'
  
  def __init__(self, source, data_field):
    super().__init__(source, data_field)
    self.__init__parent_type_and_types()

  def __init__parent_type_and_types(self):
    type_regex = re.compile(r'^((?P<map>Map\[)(?P<key>[a-zA-Z\s]+),)?(?P<array>\[)?(?P<types>[a-zA-Z\*\|\s]+)(?:\])?.*$') 
    #.* at the end because of typo in v3.1 on webhooks property Map[string, Path Item Object | Reference Object] ]
    type_search = type_regex.search(self.get_source().get_text())
    # map list object atomic
    self.parent_type = None
    self.parent_type_map_key_type = None
    if type_search.group('map'):
      self.parent_type = DataFieldType.PARENT_TYPE_MAP
      self.parent_type_map_key_type = type_search.group('key')
    elif type_search.group('array'):
      self.parent_type = DataFieldType.PARENT_TYPE_ARRAY

    types = type_search.group('types').split('|')
    self.types = []
    for t in types:
      # In swagger 2 some Any are marked as *
      if t == '*':
        t = 'Any'
      self.types.append(t.strip())

class DataField(Data, DataWithUrls):

  FIXED = 'fixed'
  PATTERNED = 'patterned'

  def __init__(self, source, data_schema, name_type):
    super().__init__(source, data_schema)
    self.__init__name()
    self.name_type = name_type
    self.__init__type()
    self.__init__is_required()
    self.__init__rich_text()
    self.__init__applies()
    DataWithUrls.__init__(self)
    self.__init__description()

  def __init__name(self):
    cell = self.get_source().get_cell_by_header_text(re.compile('^Field (Name|Pattern)$'))
    self.name = cell.get_text()

  def __init__type(self):
    cell = self.get_source().get_cell_by_header_text(re.compile('^Type$'))
    self.type = DataFieldType(cell, self)

  def __init__applies(self): 
    cell = self.get_source().get_cell_by_header_text(re.compile('^(Validity|Applies To)$'))
    if cell != None:
      self.applies = cell.get_text()

  def __init__description(self):
    cell = self.get_source().get_cell_by_header_text(re.compile('^Description$'))
    inner_html = cell.get_inner_html()
    cleaned_inner_html = inner_html
    cleaned_inner_html = re.sub(r'^\<strong\>\s*required\s*\.?\s*\<\/strong\>\s*\.?\s*\s*', '', cleaned_inner_html, flags=re.IGNORECASE)
    cleaned_inner_html = re.sub(r'(?:\.\s)(.*syntax.*rich\s*text\s*representation\.)\s*', '.', cleaned_inner_html, flags=re.IGNORECASE)
    self.description = cleaned_inner_html

  def __init__is_required(self):
    cell = self.get_source().get_cell_by_header_text(re.compile('^Description$'))
    self.is_required = cell.get_text().startswith('REQUIRED')
  
  def __init__rich_text(self):
    cell = self.get_source().get_cell_by_header_text(re.compile('^Description$'))
    rich_text_regex = re.compile(r'\.\s*(?P<format>.*)\s+syntax.*rich\stext\srepresentation\.\s*')
    rich_text_search = rich_text_regex.search(cell.get_text())
    if rich_text_search:
      self.rich_text = rich_text_search.group('format')
    else:
      self.rich_text = None

class DataSchema(Data, DataWithUrls):
  def __init__(self, source, data_schemas):
    super().__init__(source, data_schemas)
    self.__init__name()
    self.__init__is_root()
    self.__init__is_extensible()
    self.__init__description()
    DataWithUrls.__init__(self)
    self.__init__fields()
    #self.__init__urls()

  def __init__is_root(self):
    description = self.get_source().get_only_content_as_html()
    if description != None:
      self.is_root = description.__contains__('This is the root')
    else:
      self.is_root = False

  def __init__name(self):
    self.name = self.get_source().get_text()
  
  def __init__description(self):
    self.description = self.get_source().get_only_content_as_html()
    if self.get_data_parent()._description != None:
      if self.description == None:
        self.description = self.get_data_parent()._description
      else:
        self.description += self.get_data_parent()._description

  def __init__is_extensible(self):
    self.is_extensible = False 
    if self.get_data_root()._version.is_version('2'):
      patterned_fields_section = self.get_source().find_section_for_text(re.compile('^Patterned (Fields|Objects)$'))
      if patterned_fields_section != None:
        patterned_fields = self._get_fields_from_section(patterned_fields_section, DataField.PATTERNED)
        for field in patterned_fields:
          if field.name == '^x-':
            self.is_extensible = True
            break
    else:
      extension_mention = self.get_source().find_content_for_text(re.compile('This object MAY be extended with Specification Extensions.'))
      self.is_extensible = extension_mention!= None

  def _get_fields_from_section(self, section, name_type):
    fields = []
    for content in section.get_contents():
      if content.sub_type == ContentSubType.TABLE:
        for line in content.get_lines():
          fields.append(DataField(line, self, name_type))
    return fields

  def __init__fields(self):
    self.fields = []

    fixed_fields_section = self.get_source().find_section_for_text(re.compile('^Fixed Fields$'))
    if fixed_fields_section != None:
      self.fields += self._get_fields_from_section(fixed_fields_section, DataField.FIXED)

    patterned_fields_section = self.get_source().find_section_for_text(re.compile('^Patterned (Fields|Objects)$'))
    if patterned_fields_section != None:
      self.fields += self._get_fields_from_section(patterned_fields_section, DataField.PATTERNED)

    # in v3 the x- extension field is not listed (while it was in v2)
    if not self.get_data_root()._version.is_version('2'):
      specification_extensions_section = self.get_data_parent().get_source().find_section_for_text(re.compile('^Specification Extensions$'))
      if specification_extensions_section != None:
        self.fields += self._get_fields_from_section(specification_extensions_section, DataField.PATTERNED)

class DataSchemas(Data):
  def __init__(self, source, specification):
    super().__init__(source, specification)
    self.__init__description()
    self.__init__schemas()

  def __init__description(self):
    schema_section = self.get_source().find_section_for_text(re.compile('^Schema$'))
    self._description = schema_section.get_only_content_as_html()

  def __init__schemas(self):
    schema_section = self.get_source().find_section_for_text(re.compile('^Schema$'))
    self.schemas = []
    for content in schema_section.get_contents():
      if content.type == ContentType.SECTION:
        self.schemas.append(DataSchema(content, self))
